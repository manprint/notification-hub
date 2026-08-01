#!/bin/bash
set -euo pipefail

# Smoke test for NotifyHub end-to-end acceptance
# Exit codes: 0 = success, 1 = failure

COLOR_RED='\033[0;31m'
COLOR_GREEN='\033[0;32m'
COLOR_NC='\033[0m'

test_passed=0
test_failed=0

assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="$3"

    if [ "$expected" = "$actual" ]; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} $msg"
        ((test_passed++))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} $msg"
        echo "  Expected: $expected"
        echo "  Actual:   $actual"
        ((test_failed++))
        return 1
    fi
}

assert_http_code() {
    local expected="$1"
    local actual="$2"
    local msg="$3"

    if [ "$expected" = "$actual" ]; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} $msg (HTTP $actual)"
        ((test_passed++))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} $msg"
        echo "  Expected HTTP: $expected"
        echo "  Actual HTTP:   $actual"
        ((test_failed++))
        return 1
    fi
}

echo "Step 1: Starting stack..."
docker compose --profile smoke down -v 2>/dev/null || true
docker compose --profile smoke up -d
echo "  Waiting for services to be ready..."

# Wait for readyz endpoint
max_retries=90
retry=0
while [ $retry -lt $max_retries ]; do
    if curl -s -f http://localhost/readyz >/dev/null 2>&1; then
        echo "  API ready"
        break
    fi
    sleep 1
    ((retry++))
done

if [ $retry -eq $max_retries ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Services did not become ready within 90 seconds"
    docker compose --profile smoke logs
    exit 1
fi

echo -e "${COLOR_GREEN}✓${COLOR_NC} All services ready"

# Step 2: Bootstrap tenant
echo ""
echo "Step 2: Bootstrap tenant..."
bootstrap_output=$(docker compose run --rm -T migrate /bin/bash -c "cd /app && python -c \"
import asyncio
from app.core.config import config
from app.db.session import get_session
from app.models import Tenant, User
from app.core.crypto import hash_password
from sqlalchemy import insert

async def bootstrap():
    async with get_session() as session:
        # Create tenant
        tenant = await session.scalar(insert(Tenant).values(name='Test Tenant').returning(Tenant))
        await session.flush()

        # Create owner user
        user = await session.scalar(insert(User).values(
            tenant_id=tenant.id,
            email='owner@test.local',
            password_hash=hash_password('password123'),
            role='owner',
            status='active'
        ).returning(User))

        await session.commit()
        print(f'BOOTSTRAP_TENANT_ID={tenant.id}')
        print(f'BOOTSTRAP_USER_EMAIL={user.email}')

asyncio.run(bootstrap())
\"" 2>&1 || echo "BOOTSTRAP_FAILED")

if echo "$bootstrap_output" | grep -q "BOOTSTRAP_FAILED"; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Bootstrap failed"
    echo "$bootstrap_output"
    exit 1
fi

TENANT_ID=$(echo "$bootstrap_output" | grep BOOTSTRAP_TENANT_ID | cut -d= -f2)
USER_EMAIL=$(echo "$bootstrap_output" | grep BOOTSTRAP_USER_EMAIL | cut -d= -f2)

if [ -z "$TENANT_ID" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Could not extract tenant ID"
    exit 1
fi

echo -e "${COLOR_GREEN}✓${COLOR_NC} Tenant bootstrapped (ID: $TENANT_ID)"

# Step 3: Login
echo ""
echo "Step 3: Login..."
login_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$USER_EMAIL\", \"password\": \"password123\"}")

http_code=$(echo "$login_response" | tail -1)
body=$(echo "$login_response" | head -n -1)

assert_http_code 200 "$http_code" "Login should return 200"

access_token=$(echo "$body" | jq -r '.access_token // empty')
if [ -z "$access_token" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Login did not return access_token"
    echo "$body"
    exit 1
fi

echo -e "${COLOR_GREEN}✓${COLOR_NC} Login successful, access_token obtained"

# Step 4: Create group
echo ""
echo "Step 4: Create group..."
group_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/api/v1/groups \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"name": "Server Produzione", "description": "Production servers"}')

http_code=$(echo "$group_response" | tail -1)
body=$(echo "$group_response" | head -n -1)

assert_http_code 201 "$http_code" "Create group should return 201"

group_id=$(echo "$body" | jq -r '.id // empty')
if [ -z "$group_id" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Create group did not return id"
    echo "$body"
    exit 1
fi

echo -e "${COLOR_GREEN}✓${COLOR_NC} Group created (ID: $group_id)"

# Step 5: Create receiver
echo ""
echo "Step 5: Create receiver..."
receiver_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/api/v1/groups/$group_id/receivers \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"slug": "server-prod"}')

http_code=$(echo "$receiver_response" | tail -1)
body=$(echo "$receiver_response" | head -n -1)

assert_http_code 201 "$http_code" "Create receiver should return 201"

receiver_id=$(echo "$body" | jq -r '.id // empty')
receiver_slug=$(echo "$body" | jq -r '.slug // empty')
slug_length=$(echo -n "$receiver_slug" | wc -c)

if [ "$slug_length" -ne 22 ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Receiver slug should be 22 characters, got $slug_length"
    exit 1
fi

echo -e "${COLOR_GREEN}✓${COLOR_NC} Receiver created (slug: $receiver_slug, length: 22)"

# Step 6: Create delivery channel
echo ""
echo "Step 6: Create delivery channel..."
export NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST="mock-webhook"

channel_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/api/v1/delivery/channels \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"type": "slack", "webhook_url": "http://mock-webhook:8899/hook"}')

http_code=$(echo "$channel_response" | tail -1)
body=$(echo "$channel_response" | head -n -1)

assert_http_code 201 "$http_code" "Create channel should return 201"

if echo "$body" | grep -q "8899/hook"; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Channel response contains webhook URL in plain text"
    exit 1
fi

if ! echo "$body" | jq -e '.webhook_hint' >/dev/null 2>&1; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Channel response missing webhook_hint"
    exit 1
fi

channel_id=$(echo "$body" | jq -r '.id // empty')
echo -e "${COLOR_GREEN}✓${COLOR_NC} Channel created (webhook masked in response)"

# Step 7: Bind group to channel
echo ""
echo "Step 7: Bind group to channel..."
binding_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/api/v1/groups/$group_id/channels/$channel_id \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"min_severity": "error"}')

http_code=$(echo "$binding_response" | tail -1)
assert_http_code 201 "$http_code" "Bind channel should return 201"

echo -e "${COLOR_GREEN}✓${COLOR_NC} Channel bound to group with min_severity=error"

# Step 8: Create severity rule
echo ""
echo "Step 8: Create severity rule..."
rule_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/api/v1/receivers/$receiver_id/severity-rules \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"pattern": "FALL(ITO|IMENT)|ERROR", "severity": "error"}')

http_code=$(echo "$rule_response" | tail -1)
assert_http_code 201 "$http_code" "Create severity rule should return 201"

echo -e "${COLOR_GREEN}✓${COLOR_NC} Severity rule created"

# Step 9: First ingestion (should match rule)
echo ""
echo "Step 9: Ingestion with pattern match..."
ingest_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/ingest/$receiver_slug \
    -H "X-Request-Id: smoke-1" \
    -d "Backup FALLITO: disco pieno su /var")

http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)

assert_http_code 201 "$http_code" "Ingestion should return 201"

severity=$(echo "$body" | jq -r '.severity // empty')
severity_source=$(echo "$body" | jq -r '.severity_source // empty')
forwarded_to=$(echo "$body" | jq -r '.forwarded_to // empty')

assert_eq "error" "$severity" "Severity should be error"
assert_eq "rule" "$severity_source" "Severity source should be rule"
assert_eq "1" "$forwarded_to" "Should forward to 1 channel"

echo -e "${COLOR_GREEN}✓${COLOR_NC} Notification ingested and matched rule"

# Step 10: Repeat ingestion (should be idempotent)
echo ""
echo "Step 10: Repeat ingestion (idempotency check)..."
ingest_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/ingest/$receiver_slug \
    -H "X-Request-Id: smoke-1" \
    -d "Backup FALLITO: disco pieno su /var")

http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)

assert_http_code 200 "$http_code" "Repeat ingestion should return 200"

idempotent_header=$(curl -s -i -X POST http://localhost/ingest/$receiver_slug \
    -H "X-Request-Id: smoke-1" \
    -d "Backup FALLITO: disco pieno su /var" | grep -i "Idempotent-Replay" || echo "")

if [ -z "$idempotent_header" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Response missing Idempotent-Replay header"
else
    echo -e "${COLOR_GREEN}✓${COLOR_NC} Idempotent replay confirmed"
fi

# Step 11: Ingestion on non-existent slug
echo ""
echo "Step 11: Ingestion on non-existent slug..."
ingest_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/ingest/nonexistent-slug-12345678901 \
    -d "test message")

http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)

assert_http_code 404 "$http_code" "Non-existent slug should return 404"
404_nonexistent="$body"

echo -e "${COLOR_GREEN}✓${COLOR_NC} Non-existent slug returned 404"

# Step 12: Disable receiver and test 404 equivalence
echo ""
echo "Step 12: Disable receiver and verify 404 equivalence..."
disable_response=$(curl -s -w "\n%{http_code}" -X PATCH http://localhost/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"status": "disabled"}')

sleep 1  # Give cache time to clear if any

ingest_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/ingest/$receiver_slug \
    -d "test message")

http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)

assert_http_code 404 "$http_code" "Disabled receiver should return 404"

if [ "$body" != "$404_nonexistent" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} 404 body not identical for disabled receiver"
    echo "  Expected: $404_nonexistent"
    echo "  Got:      $body"
    ((test_failed++))
else
    echo -e "${COLOR_GREEN}✓${COLOR_NC} 404 body byte-identical for disabled receiver (I-2 verified)"
    ((test_passed++))
fi

# Step 13: Re-enable receiver
echo ""
echo "Step 13: Re-enable receiver..."
enable_response=$(curl -s -w "\n%{http_code}" -X PATCH http://localhost/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"status": "active"}')

http_code=$(echo "$enable_response" | tail -1)
assert_http_code 200 "$http_code" "Enable receiver should return 200"

echo -e "${COLOR_GREEN}✓${COLOR_NC} Receiver re-enabled"

# Step 14: Ingest large payload (2MB)
echo ""
echo "Step 14: Ingest 2MB payload..."
dd if=/dev/zero bs=1M count=2 2>/dev/null | base64 > /tmp/payload_2mb.txt

ingest_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/ingest/$receiver_slug \
    --data-binary @/tmp/payload_2mb.txt)

http_code=$(echo "$ingest_response" | tail -1)
body=$(echo "$ingest_response" | head -n -1)

assert_http_code 201 "$http_code" "2MB ingestion should return 201"

storage_backend=$(echo "$body" | jq -r '.storage_backend // empty')
if [ "$storage_backend" != "object" ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Large payload should use object storage, got: $storage_backend"
else
    echo -e "${COLOR_GREEN}✓${COLOR_NC} Large payload stored in object storage"
fi

notification_id=$(echo "$body" | jq -r '.id // empty')

# Step 15: Download and verify content
echo ""
echo "Step 15: Download and verify content..."
if [ -n "$notification_id" ]; then
    download_response=$(curl -s -w "\n%{http_code}" http://localhost/api/v1/notifications/$notification_id/content \
        -H "Authorization: Bearer $access_token")

    http_code=$(echo "$download_response" | tail -1)
    assert_http_code 200 "$http_code" "Download content should return 200"

    echo -e "${COLOR_GREEN}✓${COLOR_NC} Content downloaded (SHA-256 verification skipped in smoke test)"
fi

# Step 16: Wait for webhook delivery
echo ""
echo "Step 16: Verify webhook delivery..."
webhook_received=0
max_wait=30
waited=0

while [ $waited -lt $max_wait ]; do
    received=$(curl -s http://localhost:8899/_received 2>/dev/null | jq 'length' 2>/dev/null || echo "0")
    if [ "$received" -ge 1 ]; then
        webhook_received=1
        break
    fi
    sleep 1
    ((waited++))
done

if [ $webhook_received -eq 0 ]; then
    echo -e "${COLOR_RED}✗${COLOR_NC} Webhook not received within 30 seconds"
    echo "  Check worker/beat status"
    ((test_failed++))
else
    webhook_count=$(curl -s http://localhost:8899/_received | jq 'length')
    if [ "$webhook_count" -eq 1 ]; then
        echo -e "${COLOR_GREEN}✓${COLOR_NC} Webhook delivered (exactly 1 request)"
        ((test_passed++))
    else
        echo -e "${COLOR_RED}✗${COLOR_NC} Unexpected number of webhook requests: $webhook_count (expected 1)"
        ((test_failed++))
    fi
fi

# Step 17: Ingest oversized payload
echo ""
echo "Step 17: Reject oversized payload..."

# Set receiver max_body_bytes to a small value for this test
receiver_update=$(curl -s -w "\n%{http_code}" -X PATCH http://localhost/api/v1/receivers/$receiver_id \
    -H "Authorization: Bearer $access_token" \
    -H "Content-Type: application/json" \
    -d '{"max_body_bytes": 100}')

sleep 1

oversized_response=$(curl -s -w "\n%{http_code}" -X POST http://localhost/ingest/$receiver_slug \
    -d "This is a message that exceeds the configured limit and should be rejected by the ingestion endpoint")

http_code=$(echo "$oversized_response" | tail -1)
assert_http_code 413 "$http_code" "Oversized payload should return 413"

echo -e "${COLOR_GREEN}✓${COLOR_NC} Oversized payload rejected"

# Summary
echo ""
echo "======================================"
echo "Smoke test results:"
echo "  Passed: $test_passed"
echo "  Failed: $test_failed"
echo "======================================"

if [ $test_failed -eq 0 ]; then
    echo -e "${COLOR_GREEN}SMOKE OK${COLOR_NC}"
    exit 0
else
    echo -e "${COLOR_RED}SMOKE FAILED${COLOR_NC}"
    exit 1
fi
