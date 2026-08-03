#!/bin/bash
set -euo pipefail

# Smoke test end-to-end contro l'immagine all-in-one.
#
#   make all-in-one-smoke
#   ./deploy/all-in-one/smoke-all-in-one.sh [--keep]
#
# Stessi controlli di scripts/smoke.sh (che invece verifica lo stack Compose):
# stesse asserzioni, stesso ordine, adattati al container unico.
#
# Differenze necessarie rispetto all'originale:
#   - lo stack e' un solo container, avviato con docker run su una rete
#     dedicata insieme al mock del webhook;
#   - il bootstrap del tenant passa da `notifyhub-cli`, che ricostruisce
#     l'ambiente applicativo (docker exec non eredita quello dell'entrypoint);
#   - la porta pubblica e' configurabile, per non collidere con altri stack.
#
# Exit code: 0 = successo, 1 = fallimento.

COLOR_RED='\033[0;31m'
COLOR_GREEN='\033[0;32m'
COLOR_NC='\033[0m'

test_passed=0
test_failed=0

IMAGE="${SMOKE_IMAGE:-notifyhub-all-in-one:1.0.0}"
NETWORK="${SMOKE_NETWORK:-notifyhub-smoke}"
CONTAINER="${SMOKE_CONTAINER:-notifyhub-smoke}"
MOCK="${SMOKE_MOCK:-mock-webhook}"
PORT="${SMOKE_PORT:-18099}"
MOCK_PORT="${SMOKE_MOCK_PORT:-18899}"
BASE="http://127.0.0.1:${PORT}"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    if [ "$expected" = "$actual" ]; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} $msg"
        test_passed=$((test_passed+1))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} $msg"
        echo "  Atteso: $expected"
        echo "  Reale:  $actual"
        test_failed=$((test_failed+1))
    fi
}

assert_http_code() {
    local expected="$1" actual="$2" msg="$3"
    if [ "$expected" = "$actual" ]; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} $msg (HTTP $actual)"
        test_passed=$((test_passed+1))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} $msg"
        echo "  Atteso HTTP: $expected"
        echo "  Reale HTTP:  $actual"
        test_failed=$((test_failed+1))
    fi
}

cleanup() {
    [ "$KEEP" = "1" ] && { echo "Container lasciati in piedi (--keep): $CONTAINER, $MOCK"; return; }
    docker rm -f "$CONTAINER" "$MOCK" >/dev/null 2>&1 || true
    docker volume rm -f "${CONTAINER}-data" "${CONTAINER}-logs" >/dev/null 2>&1 || true
    docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Step 1: avvio dello stack a container unico..."
cleanup
trap cleanup EXIT
docker network create "$NETWORK" >/dev/null

docker run -d --name "$MOCK" --network "$NETWORK" \
    -p "127.0.0.1:${MOCK_PORT}:8899" \
    -v "${REPO_ROOT}/scripts:/scripts:ro" \
    python:3.12-slim python /scripts/mock_webhook.py >/dev/null

# mock-webhook e' l'unico host verso cui questo test invia webhook reali: deve
# stare nella allowlist letta dall'applicazione dentro al container.
docker run -d --name "$CONTAINER" --network "$NETWORK" \
    -p "127.0.0.1:${PORT}:80" \
    -e NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST="hooks.slack.com,chat.googleapis.com,${MOCK}" \
    -v "${CONTAINER}-data:/data" \
    -v "${CONTAINER}-logs:/logs" \
    "$IMAGE" >/dev/null

echo "  attendo che il container diventi healthy..."
retry=0
while [ $retry -lt 180 ]; do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo missing)
    [ "$status" = "healthy" ] && break
    if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "false" ]; then
        echo -e "${COLOR_RED}✗${COLOR_NC} Il container si e' fermato durante l'avvio"
        docker logs "$CONTAINER" | tail -30
        exit 1
    fi
    sleep 2
    retry=$((retry+1))
done

if [ "$status" != "healthy" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Il container non e' diventato healthy entro 360 secondi"
    docker inspect -f '{{range .State.Health.Log}}{{.Output}}{{end}}' "$CONTAINER" | tail -5
    exit 1
fi
echo -e "${COLOR_GREEN}✓${COLOR_NC} Container healthy: tutti i servizi sono su"

echo ""
echo "Step 2: bootstrap del tenant..."
USER_EMAIL="owner@acme-notifyhub-smoke.io"
USER_PASSWORD="password123"

bootstrap_output=$(docker exec "$CONTAINER" notifyhub-cli bootstrap \
    --tenant-name "Test Tenant" \
    --email "$USER_EMAIL" \
    --password "$USER_PASSWORD" 2>&1 || echo "BOOTSTRAP_FAILED")

if echo "$bootstrap_output" | grep -q "BOOTSTRAP_FAILED" || ! echo "$bootstrap_output" | grep -q "Tenant created"; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Bootstrap fallito"
    echo "$bootstrap_output"
    exit 1
fi
echo -e "${COLOR_GREEN}✓${COLOR_NC} Tenant creato"

echo ""
echo "Step 3: login..."
login_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$USER_EMAIL\", \"password\": \"$USER_PASSWORD\"}")
http_code=$(echo "$login_response" | tail -1)
body=$(echo "$login_response" | head -n -1)
assert_http_code 200 "$http_code" "Il login deve restituire 200"

access_token=$(echo "$body" | jq -r '.access_token // empty')
[ -n "$access_token" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Nessun access_token"; exit 1; }
echo -e "${COLOR_GREEN}✓${COLOR_NC} Login riuscito"

echo ""
echo "Step 4: creazione del gruppo..."
group_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/api/v1/groups \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"name": "Server Produzione", "description": "Production servers"}')
http_code=$(echo "$group_response" | tail -1)
body=$(echo "$group_response" | head -n -1)
assert_http_code 201 "$http_code" "La creazione del gruppo deve restituire 201"
group_id=$(echo "$body" | jq -r '.id // empty')
[ -n "$group_id" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Nessun id di gruppo"; exit 1; }
echo -e "${COLOR_GREEN}✓${COLOR_NC} Gruppo creato (ID: $group_id)"

echo ""
echo "Step 5: creazione del receiver..."
receiver_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/api/v1/groups/$group_id/receivers \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"name": "Backup notturno"}')
http_code=$(echo "$receiver_response" | tail -1)
body=$(echo "$receiver_response" | head -n -1)
assert_http_code 201 "$http_code" "La creazione del receiver deve restituire 201"
receiver_id=$(echo "$body" | jq -r '.id // empty')
receiver_slug=$(echo "$body" | jq -r '.slug // empty')
assert_eq "22" "$(echo -n "$receiver_slug" | wc -c)" "Lo slug del receiver deve essere di 22 caratteri"

echo ""
echo "Step 6: creazione del canale di consegna..."
channel_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/api/v1/channels \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d "{\"name\": \"Slack #ops\", \"type\": \"slack\", \"webhook_url\": \"http://${MOCK}:8899/hook\"}")
http_code=$(echo "$channel_response" | tail -1)
body=$(echo "$channel_response" | head -n -1)
assert_http_code 201 "$http_code" "La creazione del canale deve restituire 201"

if echo "$body" | grep -q "8899/hook"; then
    echo -e "${COLOR_RED}✗${COLOR_NC} La risposta contiene la webhook URL in chiaro"
    test_failed=$((test_failed+1))
else
    echo -e "${COLOR_GREEN}✓${COLOR_NC} Webhook mascherata nella risposta"
    test_passed=$((test_passed+1))
fi
channel_id=$(echo "$body" | jq -r '.id // empty')

echo ""
echo "Step 7: associazione gruppo-canale..."
binding_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/api/v1/groups/$group_id/channels \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d "{\"channel_id\": \"$channel_id\", \"min_severity\": \"error\"}")
assert_http_code 201 "$(echo "$binding_response" | tail -1)" "L'associazione del canale deve restituire 201"

echo ""
echo "Step 8: creazione della regola di severity..."
rule_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/api/v1/receivers/$receiver_id/severity-rules \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"priority": 0, "pattern": "FALL(ITO|IMENT)|ERROR", "severity": "error"}')
assert_http_code 201 "$(echo "$rule_response" | tail -1)" "La creazione della regola deve restituire 201"

echo ""
echo "Step 9: ingestion con match della regola..."
ingest_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/ingest/$receiver_slug \
    -H "X-Request-Id: smoke-1" -d "Backup FALLITO: disco pieno su /var")
http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)
assert_http_code 201 "$http_code" "L'ingestion deve restituire 201"
assert_eq "error" "$(echo "$body" | jq -r '.severity // empty')" "La severity deve essere error"
assert_eq "rule" "$(echo "$body" | jq -r '.severity_source // empty')" "La severity deve venire dalla regola"
assert_eq "1" "$(echo "$body" | jq -r '.forwarded_to // empty')" "Deve inoltrare a 1 canale"

echo ""
echo "Step 10: ingestion ripetuta (idempotenza)..."
ingest_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/ingest/$receiver_slug \
    -H "X-Request-Id: smoke-1" -d "Backup FALLITO: disco pieno su /var")
assert_http_code 200 "$(echo "$ingest_response" | tail -1)" "L'ingestion ripetuta deve restituire 200"

idempotent_header=$(curl -s -i -X POST $BASE/ingest/$receiver_slug \
    -H "X-Request-Id: smoke-1" -d "Backup FALLITO: disco pieno su /var" | grep -i "Idempotent-Replay" || echo "")
if [ -z "$idempotent_header" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Manca l'header Idempotent-Replay"
    test_failed=$((test_failed+1))
else
    echo -e "${COLOR_GREEN}✓${COLOR_NC} Replay idempotente confermato"
    test_passed=$((test_passed+1))
fi

echo ""
echo "Step 11: ingestion su slug inesistente..."
ingest_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/ingest/nonexistent-slug-12345678901 -d "test message")
http_code=$(echo "$ingest_response" | tail -1)
body_404_nonexistent=$(echo "$ingest_response" | head -n -1)
assert_http_code 404 "$http_code" "Uno slug inesistente deve restituire 404"

echo ""
echo "Step 12: receiver disabilitato, 404 identico..."
curl -s -o /dev/null -X PATCH $BASE/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"status": "disabled"}'
sleep 1
ingest_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/ingest/$receiver_slug -d "test message")
http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)
assert_http_code 404 "$http_code" "Un receiver disabilitato deve restituire 404"
assert_eq "$body_404_nonexistent" "$body" "Il corpo del 404 deve essere identico byte a byte (I-2)"

echo ""
echo "Step 13: riabilitazione del receiver..."
enable_response=$(curl -s -w "\n%{http_code}" -X PATCH $BASE/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"status": "active"}')
assert_http_code 200 "$(echo "$enable_response" | tail -1)" "La riabilitazione deve restituire 200"

echo ""
echo "Step 14: ingestion di un payload da 2MB..."
cap_response=$(curl -s -w "\n%{http_code}" -X PATCH $BASE/api/v1/tenant \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"max_body_bytes": 5242880}')
assert_http_code 200 "$(echo "$cap_response" | tail -1)" "Alzare il cap del tenant deve restituire 200"

cap_response=$(curl -s -w "\n%{http_code}" -X PATCH $BASE/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"max_body_bytes": 5242880}')
assert_http_code 200 "$(echo "$cap_response" | tail -1)" "Alzare il cap del receiver deve restituire 200"

dd if=/dev/zero bs=1M count=2 2>/dev/null > /tmp/payload_2mb.txt
ingest_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/ingest/$receiver_slug \
    -H "Content-Type: text/plain" --data-binary @/tmp/payload_2mb.txt)
http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)
assert_http_code 201 "$http_code" "L'ingestion da 2MB deve restituire 201"
assert_eq "object" "$(echo "$body" | jq -r '.storage_backend // empty')" "Il payload grande deve finire su MinIO"
notification_id=$(echo "$body" | jq -r '.id // empty')

echo ""
echo "Step 15: download e verifica del contenuto..."
if [ -n "$notification_id" ]; then
    http_code=$(curl -s -o /tmp/payload_2mb_downloaded.txt -w "%{http_code}" \
        $BASE/api/v1/notifications/$notification_id/content -H "Authorization: Bearer $access_token")
    assert_http_code 200 "$http_code" "Il download del contenuto deve restituire 200"
    if cmp -s /tmp/payload_2mb.txt /tmp/payload_2mb_downloaded.txt; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} Contenuto scaricato identico ai 2097152 byte caricati"
        test_passed=$((test_passed+1))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} Il contenuto scaricato differisce dall'originale"
        test_failed=$((test_failed+1))
    fi
fi

echo ""
echo "Step 16: consegna del webhook..."
webhook_received=0
waited=0
while [ $waited -lt 30 ]; do
    received=$(curl -s http://127.0.0.1:${MOCK_PORT}/_received 2>/dev/null | jq 'length' 2>/dev/null || echo "0")
    if [ "$received" -ge 1 ]; then webhook_received=1; break; fi
    sleep 1
    waited=$((waited+1))
done

if [ $webhook_received -eq 0 ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Webhook non ricevuto entro 30 secondi"
    docker logs "$CONTAINER" 2>&1 | grep '^\[worker\]' | tail -10
    test_failed=$((test_failed+1))
else
    webhook_count=$(curl -s http://127.0.0.1:${MOCK_PORT}/_received | jq 'length')
    assert_eq "1" "$webhook_count" "Il webhook deve essere consegnato esattamente una volta"
fi

echo ""
echo "Step 17: rifiuto del payload sovradimensionato..."
curl -s -o /dev/null -X PATCH $BASE/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" -H "Content-Type: application/json" \
    -d '{"max_body_bytes": 100}'
sleep 1
oversized_response=$(curl -s -w "\n%{http_code}" -X POST $BASE/ingest/$receiver_slug \
    -d "This is a message that is well over one hundred bytes long and therefore exceeds the configured per-receiver limit of 100 bytes set just above")
assert_http_code 413 "$(echo "$oversized_response" | tail -1)" "Un payload sovradimensionato deve restituire 413"

echo ""
echo "======================================"
echo "Risultati dello smoke test all-in-one:"
echo "  Passati: $test_passed"
echo "  Falliti: $test_failed"
echo "======================================"

if [ $test_failed -eq 0 ]; then
    echo -e "${COLOR_GREEN}SMOKE OK${COLOR_NC}"
    exit 0
else
    echo -e "${COLOR_RED}SMOKE FAILED${COLOR_NC}"
    exit 1
fi
