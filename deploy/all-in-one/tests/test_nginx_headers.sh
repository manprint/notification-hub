#!/usr/bin/env bash
# Verifica con un nginx reale la configurazione della SPA nell'all-in-one: il template viene
# reso come fa nginx_render_conf dell'entrypoint, poi si controllano cache di index.html e
# degli asset, 404 per gli asset mancanti e intestazioni di sicurezza su ogni risposta della SPA.
# Richiede Docker. Uso: deploy/all-in-one/tests/test_nginx_headers.sh (IMAGE=... per un'altra immagine nginx)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${HERE}/../config/nginx.conf"
IMAGE="${IMAGE:-nginx:alpine}"
NAME="nh-aio-nginx-check-$$"
TMP="$(mktemp -d)"
trap 'docker rm -f "${NAME}" >/dev/null 2>&1 || true; rm -rf "${TMP}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

# Stessi segnaposti di nginx_render_conf. Il comando `user notifyhub` non esiste nell'immagine
# di prova, e i percorsi sotto /run/notifyhub li crea il comando del container.
sed -e 's|__CLIENT_MAX_BODY__|20971520|g' -e 's|__API_PORT__|8000|g' \
    -e '/^user /d' "${TEMPLATE}" > "${TMP}/nginx.conf"
mkdir -p "${TMP}/html/assets"
echo '<!doctype html><title>NotifyHub</title>' > "${TMP}/html/index.html"
echo 'console.log("ok");' > "${TMP}/html/assets/app-abc123.js"

PREPARA='mkdir -p /run/notifyhub/nginx/client_body /run/notifyhub/nginx/proxy'
MONTAGGI=(
  -v "${TMP}/nginx.conf:/etc/nginx/nginx.conf:ro"
  -v "${TMP}/html:/usr/share/notifyhub/html:ro"
)

docker run --rm "${MONTAGGI[@]}" "${IMAGE}" sh -c "${PREPARA} && nginx -t" >/dev/null 2>&1 \
  || fail "nginx -t sul template all-in-one"

docker run -d --name "${NAME}" -p 127.0.0.1::80 "${MONTAGGI[@]}" "${IMAGE}" \
  sh -c "${PREPARA} && exec nginx -g 'daemon off;'" >/dev/null
PORT="$(docker port "${NAME}" 80/tcp | head -n1 | awk -F: '{print $NF}')"
BASE="http://127.0.0.1:${PORT}"

for _ in $(seq 1 30); do
  curl -fs -o /dev/null "${BASE}/index.html" && break
  sleep 1
done

# intestazioni URL: tutte le intestazioni della risposta HEAD, senza CR.
intestazioni() {
  local risposta
  risposta="$(curl -sI "$1")"
  printf '%s\n' "${risposta//$'\r'/}"
}

# ha_intestazione REGEX URL: vero se la risposta HEAD di URL ha una riga che corrisponde.
# Le variabili con la risposta si confrontano con here-string, senza pipe: con pipefail
# un grep -q che esce in anticipo farebbe fallire echo con SIGPIPE.
ha_intestazione() {
  local risposta
  risposta="$(intestazioni "$2")"
  grep -qi "$1" <<<"${risposta}"
}

ha_intestazione '^cache-control: no-cache' "${BASE}/index.html" || fail "index.html senza no-cache"
ha_intestazione '^cache-control: no-cache' "${BASE}/" || fail "/ (fallback SPA) senza no-cache"
ha_intestazione '^cache-control: max-age=31536000' "${BASE}/assets/app-abc123.js" \
  || fail "asset con hash senza cache lunga"

code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/assets/missing.js")"
[ "${code}" = "404" ] || fail "asset mancante risponde ${code}, atteso 404"

# Le intestazioni di sicurezza devono valere su tutte le risposte della SPA, anche quelle
# con una location che imposta la cache: e' la regressione che questo test copre.
for url in "${BASE}/index.html" "${BASE}/" "${BASE}/assets/app-abc123.js"; do
  ha_intestazione '^x-frame-options: DENY' "${url}" || fail "manca X-Frame-Options su ${url}"
  ha_intestazione '^x-content-type-options: nosniff' "${url}" || fail "manca nosniff su ${url}"
  ha_intestazione '^referrer-policy: strict-origin-when-cross-origin' "${url}" \
    || fail "manca Referrer-Policy su ${url}"
done
ha_intestazione '^server: nginx$' "${BASE}/index.html" || fail "server_tokens non disattivato"

echo "OK: nginx all-in-one (${IMAGE})"
