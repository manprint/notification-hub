#!/usr/bin/env bash
# Test di head_immagine di upgrade-all-in-one.sh: la revisione attesa dopo
# l'aggiornamento deve venire dall'immagine di destinazione, con un docker finto
# che restituisce il contenuto della cartella delle migrazioni.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=helpers.sh
. "${HERE}/helpers.sh"

sandbox_new
trap sandbox_clean EXIT

UPGRADE="${HERE}/../upgrade-all-in-one.sh"
TO_IMAGE="notifyhub-all-in-one:test"
export TO_IMAGE

# docker finto: registra gli argomenti e stampa le migrazioni di una immagine
# che ha 0016 come testa, con file non di revisione in mezzo.
cat > "${SANDBOX}/bin/docker" <<STUB
#!/bin/bash
echo "\$*" >> "${SANDBOX}/docker.calls"
cat <<'LISTING'
__pycache__
env.py
script.py.mako
0001_iniziale.py
0015_ricerca_contenuto_completo.py
0016_audit_events.py
README
LISTING
STUB
chmod +x "${SANDBOX}/bin/docker"

eval "$(extract_fn head_immagine "${UPGRADE}")"

check "head_immagine esiste nello script di upgrade" \
    declare -F head_immagine
check "head_immagine legge la revisione piu' alta dall'immagine (0016)" \
    [ "$(head_immagine)" = "0016" ]
check "head_immagine lancia l'immagine di destinazione con entrypoint sh" \
    grep -q -- "run --rm --entrypoint sh ${TO_IMAGE}" "${SANDBOX}/docker.calls"

summary
