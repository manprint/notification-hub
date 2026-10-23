#!/usr/bin/env bash
# Test di scripts/smoke.sh senza Docker ne' NotifyHub.
#
#  1. progetto compose e porte: con docker e curl finti lo script, che non
#     riesce a raggiungere /readyz, deve uscire con errore dopo aver usato solo
#     il progetto notifyhub-smoke e la porta dello smoke test. Il down -v non
#     deve mai riguardare il progetto di sviluppo.
#  2. controlli che non sono assert_*: un header o un backend mancante fa
#     fallire il riepilogo, cioe' l'exit code.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=helpers.sh
. "${HERE}/helpers.sh"
SMOKE="${HERE}/../../../scripts/smoke.sh"

sandbox_new
trap sandbox_clean EXIT
CALLS="${SANDBOX}/docker.calls"

cat > "${SANDBOX}/bin/docker" <<STUB
#!/bin/bash
printf 'HTTP_PORT=%s SMOKE_WEBHOOK_PORT=%s MINIO_CONSOLE_PORT=%s args:%s\n' "\${HTTP_PORT:-}" "\${SMOKE_WEBHOOK_PORT:-}" "\${MINIO_CONSOLE_PORT:-}" "\$*" >> "${CALLS}"
exit 0
STUB
# curl non raggiunge mai l'API; sleep non aspetta: il readyz scade subito.
printf '#!/bin/bash\nexit 7\n' > "${SANDBOX}/bin/curl"
printf '#!/bin/bash\nexit 0\n' > "${SANDBOX}/bin/sleep"
chmod +x "${SANDBOX}/bin/docker" "${SANDBOX}/bin/curl" "${SANDBOX}/bin/sleep"

# --- 1. progetto compose e porte ---------------------------------------------
# Con HTTP_PORT=80 nell'ambiente (stack di sviluppo) lo smoke test resta sulla
# sua porta.
out="$(HTTP_PORT=80 timeout 120 bash "${SMOKE}" 2>&1)"
rc=$?
check "smoke senza API raggiungibile: esito non zero" [ "${rc}" -ne 0 ]
check "smoke senza API raggiungibile: messaggio di readiness" \
    grep -q 'Services did not become ready' <<<"${out}"
check "smoke: ogni comando docker usa il progetto notifyhub-smoke" \
    bash -c "[ -s '${CALLS}' ] && ! grep -qvF 'args:compose -p notifyhub-smoke --profile smoke' '${CALLS}'"
check "smoke: il down -v riguarda solo il progetto notifyhub-smoke" \
    grep -qF 'args:compose -p notifyhub-smoke --profile smoke down -v' "${CALLS}"
check "smoke: porta HTTP propria, non quella dello sviluppo" \
    grep -qF 'HTTP_PORT=18080 ' "${CALLS}"
check "smoke: webhook su una porta propria" \
    grep -qF 'SMOKE_WEBHOOK_PORT=18899 ' "${CALLS}"
check "smoke: console MinIO su una porta propria" \
    grep -qF 'MINIO_CONSOLE_PORT=19001 ' "${CALLS}"

# --- 2. controlli dell'idempotenza e dello storage ---------------------------
# Colori usati dalle funzioni estratte da smoke.sh.
export COLOR_RED='\033[0;31m' COLOR_GREEN='\033[0;32m' COLOR_NC='\033[0m'
eval "$(extract_fn check_idempotent_replay "${SMOKE}")"
eval "$(extract_fn check_storage_backend "${SMOKE}")"
eval "$(extract_fn riepilogo "${SMOKE}")"

azzera() { test_passed=0; test_failed=0; }

azzera
check_idempotent_replay "" >/dev/null
check "header Idempotent-Replay assente: conteggio fallimenti" [ "${test_failed}" -eq 1 ]
riepilogo >/dev/null 2>&1
check "header Idempotent-Replay assente: il riepilogo esce con errore" [ "$?" -ne 0 ]

azzera
check_storage_backend "inline" >/dev/null
check "payload da 2 MB inline: conteggio fallimenti" [ "${test_failed}" -eq 1 ]
riepilogo >/dev/null 2>&1
check "payload da 2 MB inline: il riepilogo esce con errore" [ "$?" -ne 0 ]

azzera
check_idempotent_replay "Idempotent-Replay: true" >/dev/null
check_storage_backend "object" >/dev/null
check "controlli superati: nessun fallimento" [ "${test_failed}" -eq 0 ]
check "controlli superati: conteggio dei successi" [ "${test_passed}" -eq 2 ]
riepilogo >/dev/null 2>&1
check "controlli superati: il riepilogo esce con successo" [ "$?" -eq 0 ]

summary
