#!/usr/bin/env bash
# Il controllo dello slug nello script wrapper di smoke-all-in-one.sh non deve
# fallire a caso sotto pipefail. Il test estrae il blocco dallo script vero e lo
# esegue su un corpo di circa 25 KB con lo slug vicino all'inizio, come nel
# wrapper servito: con la pipeline `echo | head | grep -q` il controllo falliva
# in una parte delle esecuzioni.
#   test_smoke_wrapper_slug.sh [PERCORSO_DI_SMOKE_ALL_IN_ONE]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE="${1:-${HERE}/../smoke-all-in-one.sh}"
RUNS=60
SLUG="maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/nh-smoke.XXXXXX")"
trap 'rm -rf "${SANDBOX}"' EXIT

# Il blocco va dall'assegnazione di script_body fino al fi di chiusura.
sed -n '/^script_body=/,/^fi$/p' "${SMOKE}" > "${SANDBOX}/blocco.sh"
if [ ! -s "${SANDBOX}/blocco.sh" ]; then
    echo "FAIL - blocco del controllo dello slug non trovato in ${SMOKE}"
    exit 1
fi

# Corpo simile al wrapper servito: slug a riga 61, il resto e' testo.
{
    echo '#!/bin/bash'
    for i in $(seq 2 60); do echo "# riga di intestazione ${i}"; done
    echo "SLUG=\"\${NOTIFYHUB_SLUG:-${SLUG}}\""
    for i in $(seq 1 400); do echo "echo 'riga di corpo ${i} del wrapper, abbastanza lunga da riempire il file'"; done
} > "${SANDBOX}/corpo.sh"
# shellcheck disable=SC2034 # letti dal blocco sorgente
script_response="$(cat "${SANDBOX}/corpo.sh")"$'\n'"200"
fallimenti=0
for _ in $(seq 1 "${RUNS}"); do
    esito=$(
        set -eo pipefail
        # shellcheck disable=SC2034 # letto dal blocco sorgente
        receiver_slug="${SLUG}"
        # shellcheck disable=SC1090
        . "${SANDBOX}/blocco.sh"
        echo ok
    ) || true
    [ "${esito}" = "ok" ] || fallimenti=$((fallimenti + 1))
done

if [ "${fallimenti}" -eq 0 ]; then
    echo "ok   - controllo dello slug superato in ${RUNS} esecuzioni su 25 KB"
    exit 0
fi
echo "FAIL - controllo dello slug fallito in ${fallimenti} esecuzioni su ${RUNS}"
exit 1
