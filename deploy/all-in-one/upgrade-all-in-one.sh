#!/bin/bash
set -uo pipefail

# Test di AGGIORNAMENTO dell'immagine all-in-one sullo stesso volume /data.
#
#   make all-in-one-upgrade
#   ./deploy/all-in-one/upgrade-all-in-one.sh [--keep]
#
# smoke-all-in-one.sh verifica che UNA versione funzioni da installazione nuova.
# Questo verifica l'altra meta': che un'installazione gia' popolata dalla
# versione precedente sopravviva al cambio di tag, che e' l'unica procedura di
# aggiornamento documentata (README dell'all-in-one, "Aggiornamenti").
#
# Scaletta:
#   1. avvia UPGRADE_FROM_IMAGE su volumi nuovi e ci scrive dei dati veri;
#   2. ferma il container lasciando i volumi;
#   3. avvia UPGRADE_TO_IMAGE sugli STESSI volumi;
#   4. verifica che i dati di prima ci siano ancora, che le migrazioni siano
#      arrivate in testa, che il backup pre-aggiornamento esista e che le
#      funzioni nuove valgano anche per le righe scritte dalla versione vecchia.
#
# Exit code: 0 = successo, 1 = fallimento.

COLOR_RED='\033[0;31m'
COLOR_GREEN='\033[0;32m'
COLOR_NC='\033[0m'

test_passed=0
test_failed=0

FROM_IMAGE="${UPGRADE_FROM_IMAGE:-ghcr.io/manprint/notification-hub:v0.0.2}"
TO_IMAGE="${UPGRADE_TO_IMAGE:-notifyhub-all-in-one:latest}"
CONTAINER="${UPGRADE_CONTAINER:-notifyhub-upgrade}"
PORT="${UPGRADE_PORT:-18097}"
BASE="http://127.0.0.1:${PORT}"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

USER_EMAIL="owner@acme-notifyhub-upgrade.io"
USER_PASSWORD="password123"

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

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} $msg"
        test_passed=$((test_passed+1))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} $msg"
        echo "  Non contiene: $needle"
        test_failed=$((test_failed+1))
    fi
}

cleanup() {
    [ "$KEEP" = "1" ] && { echo "Container e volumi lasciati in piedi (--keep): $CONTAINER"; return; }
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker volume rm -f "${CONTAINER}-data" "${CONTAINER}-logs" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# I volumi sopravvivono al container: e' esattamente cio' che rende il test
# significativo, il /data di prima viene riaperto dall'immagine nuova.
avvia() {
    local image="$1" fase="$2"
    docker run -d --name "$CONTAINER" \
        -p "127.0.0.1:${PORT}:80" \
        -v "${CONTAINER}-data:/data" \
        -v "${CONTAINER}-logs:/logs" \
        "$image" >/dev/null

    echo "  [$fase] attendo che il container diventi healthy..."
    local retry=0 status=missing
    while [ $retry -lt 180 ]; do
        status=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo missing)
        [ "$status" = "healthy" ] && break
        if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "false" ]; then
            echo -e "${COLOR_RED}✗${COLOR_NC} [$fase] il container si e' fermato durante l'avvio"
            docker logs "$CONTAINER" 2>&1 | tail -40
            exit 1
        fi
        sleep 2
        retry=$((retry+1))
    done
    if [ "$status" != "healthy" ]; then
        echo -e "${COLOR_RED}✗${COLOR_NC} [$fase] il container non e' diventato healthy entro 360 secondi"
        docker logs "$CONTAINER" 2>&1 | tail -40
        exit 1
    fi
    echo -e "${COLOR_GREEN}✓${COLOR_NC} [$fase] container healthy ($image)"
}

# alembic dentro al container vuole l'ambiente ricostruito dall'entrypoint:
# la tabella alembic_version letta da psql dice la stessa cosa senza dipendenze.
revisione_schema() {
    docker exec "$CONTAINER" su -s /bin/sh postgres \
        -c "psql -tAc 'SELECT version_num FROM alembic_version' notifyhub" 2>/dev/null \
        | tr -d '[:space:]'
}

login() {
    curl -s -X POST "$BASE/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$USER_EMAIL\", \"password\": \"$USER_PASSWORD\"}" \
        | jq -r '.access_token // empty'
}

echo "=== Aggiornamento all-in-one: ${FROM_IMAGE} -> ${TO_IMAGE} ==="
if ! docker image inspect "$TO_IMAGE" >/dev/null 2>&1; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Immagine di destinazione assente: $TO_IMAGE (esegui prima 'make all-in-one-build')"
    exit 1
fi

cleanup
trap cleanup EXIT

echo ""
echo "Step 1: installazione con la versione di partenza..."
avvia "$FROM_IMAGE" "prima"

bootstrap_output=$(docker exec "$CONTAINER" notifyhub-cli bootstrap \
    --tenant-name "Test Tenant" \
    --email "$USER_EMAIL" \
    --password "$USER_PASSWORD" 2>&1 || echo "BOOTSTRAP_FAILED")
assert_contains "$bootstrap_output" "Tenant created" "Bootstrap sulla versione di partenza"

token=$(login)
[ -n "$token" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Nessun access_token prima dell'aggiornamento"; exit 1; }

group_id=$(curl -s -X POST "$BASE/api/v1/groups" \
    -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    -d '{"name": "Server Produzione", "description": "Production servers"}' | jq -r '.id // empty')
[ -n "$group_id" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Nessun gruppo creato"; exit 1; }

receiver_slug=$(curl -s -X POST "$BASE/api/v1/groups/$group_id/receivers" \
    -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    -d '{"name": "Backup notturno"}' | jq -r '.slug // empty')
[ -n "$receiver_slug" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Nessun receiver creato"; exit 1; }

# Un secondo receiver che non ricevera' mai nulla: dopo l'aggiornamento deve
# comparire nel riepilogo con i contatori a zero.
receiver_muto_id=$(curl -s -X POST "$BASE/api/v1/groups/$group_id/receivers" \
    -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    -d '{"name": "Job mai partito"}' | jq -r '.id // empty')
[ -n "$receiver_muto_id" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Nessun secondo receiver creato"; exit 1; }

# L'ago sta oltre i 4096 caratteri di content_preview: e' la riga che la ricerca
# della versione vecchia NON sapeva trovare, scritta dalla versione vecchia.
AGO="ago-oltre-la-preview-9f3c1d"
corpo_lungo=$(printf 'testa-del-messaggio\n'; for _ in $(seq 1 600); do printf 'riga di riempimento del log\n'; done; printf '%s\n' "$AGO")
curl -s -o /dev/null -X POST "$BASE/ingest/$receiver_slug" \
    -H "X-Request-Id: upgrade-1" --data-binary "$corpo_lungo"
curl -s -o /dev/null -X POST "$BASE/ingest/$receiver_slug" \
    -H "X-Request-Id: upgrade-2" -d "Backup FALLITO: disco pieno su /var"
curl -s -o /dev/null -X POST "$BASE/ingest/$receiver_slug" \
    -H "X-Request-Id: upgrade-3" -d "tutto regolare"

notifiche_prima=$(curl -s "$BASE/api/v1/notifications?limit=100" \
    -H "Authorization: Bearer $token" | jq -r '.notifications | length')
assert_eq "3" "$notifiche_prima" "Tre notifiche scritte dalla versione di partenza"

rev_prima=$(revisione_schema)
echo "  revisione di schema prima: ${rev_prima:-sconosciuta}"

echo ""
echo "Step 2: cambio del tag dell'immagine sullo stesso /data..."
docker rm -f "$CONTAINER" >/dev/null
avvia "$TO_IMAGE" "dopo"

echo ""
echo "Step 3: verifiche sullo stato migrato..."
rev_dopo=$(revisione_schema)
assert_eq "0015" "$rev_dopo" "Lo schema e' salito alla revisione della ricerca sul contenuto intero"
[ "$rev_prima" != "$rev_dopo" ] || echo "  (nota: lo schema non e' cambiato, la revisione di partenza era gia' ${rev_prima})"

# L'entrypoint fa un dump prima di migrare: se l'aggiornamento va storto, i dati
# della versione precedente sono ancora recuperabili.
backup_list=$(docker exec "$CONTAINER" sh -lc 'ls /data/backups 2>/dev/null' || echo "")
assert_contains "$backup_list" "pre-" "Backup pre-aggiornamento presente in /data/backups"

echo ""
echo "Step 4: i dati della versione precedente sono intatti..."
token=$(login)
[ -n "$token" ] || { echo -e "${COLOR_RED}✗${COLOR_NC} Login fallito dopo l'aggiornamento"; exit 1; }
echo -e "${COLOR_GREEN}✓${COLOR_NC} Le credenziali create dalla versione precedente funzionano ancora"
test_passed=$((test_passed+1))

notifiche_dopo=$(curl -s "$BASE/api/v1/notifications?limit=100" \
    -H "Authorization: Bearer $token" | jq -r '.notifications | length')
assert_eq "3" "$notifiche_dopo" "Le tre notifiche di prima sono ancora leggibili"

http_code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/ingest/$receiver_slug" \
    -H "X-Request-Id: upgrade-4" -d "notifica dopo l'aggiornamento")
assert_eq "201" "$http_code" "Lo slug emesso dalla versione precedente accetta ancora ingestion"

echo ""
echo "Step 5: le funzioni nuove valgono anche sulle righe vecchie..."
trovate=$(curl -s "$BASE/api/v1/notifications?q=$AGO" \
    -H "Authorization: Bearer $token" | jq -r '.notifications | length')
assert_eq "1" "$trovate" "La ricerca trova l'ago oltre i 4096 caratteri in una riga scritta prima dell'aggiornamento"

summary=$(curl -s "$BASE/api/v1/stats/summary" -H "Authorization: Bearer $token")
receivers_json=$(echo "$summary" | jq -c --arg g "$group_id" '.by_group[] | select(.group_id == $g) | .receivers')
assert_eq "2" "$(echo "$receivers_json" | jq -r 'length')" \
    "Il riepilogo elenca entrambi i receiver del gruppo"
assert_eq "0" "$(echo "$receivers_json" | jq -r --arg r "$receiver_muto_id" '.[] | select(.receiver_id == $r) | .total')" \
    "Il receiver che non ha mai scritto compare con totale zero"
assert_eq "4" "$(echo "$summary" | jq -r --arg g "$group_id" '.by_group[] | select(.group_id == $g) | .total')" \
    "Il totale del gruppo comprende le notifiche scritte prima e dopo l'aggiornamento"

echo ""
echo "======================================"
echo -e "Passati:  ${COLOR_GREEN}${test_passed}${COLOR_NC}"
echo -e "Falliti:  ${COLOR_RED}${test_failed}${COLOR_NC}"
echo "======================================"
[ "$test_failed" -eq 0 ] || exit 1
echo -e "${COLOR_GREEN}Aggiornamento ${FROM_IMAGE} -> ${TO_IMAGE} verificato.${COLOR_NC}"
