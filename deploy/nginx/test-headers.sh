#!/bin/bash
# Verifica la configurazione nginx della SPA con un nginx reale: sintassi, cache di index.html,
# 404 per gli asset mancanti, intestazioni di sicurezza. Richiede docker.
#
# Uso: deploy/nginx/test-headers.sh   (IMAGE=... per usare un'altra immagine nginx)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${IMAGE:-nginx:alpine}"
NAME="nh-nginx-check-$$"
TMP="$(mktemp -d)"
trap 'docker rm -f "${NAME}" >/dev/null 2>&1 || true; rm -rf "${TMP}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

# Il config fa proxy_pass verso api:8000: nginx -t risolve il nome, quindi serve un alias.
docker run --rm --add-host api:127.0.0.1 \
  -v "${DIR}/nginx.conf:/etc/nginx/nginx.conf:ro" "${IMAGE}" nginx -t >/dev/null 2>&1 \
  || fail "nginx -t"

mkdir -p "${TMP}/html/assets"
echo '<!doctype html><title>NotifyHub</title>' > "${TMP}/html/index.html"
echo 'console.log("ok");' > "${TMP}/html/assets/app-abc123.js"

docker run -d --name "${NAME}" -p 127.0.0.1::80 --add-host api:127.0.0.1 \
  -v "${DIR}/nginx.conf:/etc/nginx/nginx.conf:ro" \
  -v "${TMP}/html:/usr/share/nginx/html:ro" "${IMAGE}" >/dev/null
PORT="$(docker port "${NAME}" 80/tcp | head -n1 | awk -F: '{print $NF}')"
BASE="http://127.0.0.1:${PORT}"

for _ in $(seq 1 30); do
  curl -fs -o /dev/null "${BASE}/index.html" && break
  sleep 1
done

intestazioni() { curl -sI "$1" | tr -d '\r'; }

intestazioni "${BASE}/index.html" | grep -qi '^cache-control: no-cache' || fail "index.html senza no-cache"
intestazioni "${BASE}/" | grep -qi '^cache-control: no-cache' || fail "/ (fallback SPA) senza no-cache"

intestazioni "${BASE}/assets/app-abc123.js" | grep -qi '^cache-control: max-age=31536000' \
  || fail "asset con hash senza cache lunga"

code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/assets/missing.js")"
[ "${code}" = "404" ] || fail "asset mancante risponde ${code}, atteso 404"

head_resp="$(intestazioni "${BASE}/index.html")"
echo "${head_resp}" | grep -qi '^x-frame-options: DENY' || fail "manca X-Frame-Options"
echo "${head_resp}" | grep -qi '^x-content-type-options: nosniff' || fail "manca nosniff"
echo "${head_resp}" | grep -qi '^referrer-policy: strict-origin-when-cross-origin' \
  || fail "manca Referrer-Policy"
echo "${head_resp}" | grep -qi '^server: nginx$' || fail "server_tokens non disattivato"

echo "OK: nginx SPA (${IMAGE})"
