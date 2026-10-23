#!/usr/bin/env bash
# Test di funzioni dell'entrypoint in isolamento: pg_hba.conf e limite del corpo
# delle richieste in nginx. Le funzioni si estraggono dallo script, perche'
# sorgerlo lancerebbe boot.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=helpers.sh
. "${HERE}/helpers.sh"

sandbox_new
trap sandbox_clean EXIT
# shellcheck source=/dev/null
. "${SANDBOX}/lib/lib.sh"

ENTRY="${ROOTFS}/bin/notifyhub-entrypoint"
# chown e' un no-op: i test non girano come postgres ne' come notifyhub.
printf '#!/bin/bash\nexit 0\n' > "${SANDBOX}/bin/chown"
chmod +x "${SANDBOX}/bin/chown"

# --- pg_hba.conf -------------------------------------------------------------
PGDATA="${SANDBOX}/pgdata"
mkdir -p "${PGDATA}"
eval "$(extract_fn pg_write_hba "${ENTRY}")"
pg_write_hba
HBA="${PGDATA}/pg_hba.conf"

check "pg_hba: nessuna regola trust sul socket locale" \
    none_match "^local[[:space:]]+all[[:space:]]+all[[:space:]]+trust" "${HBA}"
check "pg_hba: il superutente postgres passa solo per peer" \
    grep -Eq '^local[[:space:]]+all[[:space:]]+postgres[[:space:]]+peer' "${HBA}"
check "pg_hba: gli altri ruoli sul socket chiedono la password" \
    grep -Eq '^local[[:space:]]+all[[:space:]]+all[[:space:]]+scram-sha-256' "${HBA}"
check "pg_hba: la regola peer precede quella generica" \
    bash -c "[ \$(grep -nE '^local[[:space:]]+all[[:space:]]+postgres' '${HBA}' | cut -d: -f1) -lt \$(grep -nE '^local[[:space:]]+all[[:space:]]+all' '${HBA}' | cut -d: -f1) ]"

# --- limite del corpo in nginx ----------------------------------------------
# nginx_render_conf usa il template di rootfs: si riscrivono solo i percorsi
# assoluti, perche' la sandbox non ha /etc/notifyhub e /run/notifyhub.
RUN_DIR="${SANDBOX}/run"
mkdir -p "${RUN_DIR}"
cp "${HERE}/../config/nginx.conf" "${SANDBOX}/nginx.tpl"
eval "$(extract_fn nginx_render_conf "${ENTRY}" | sed "s|/etc/notifyhub/nginx.conf|${SANDBOX}/nginx.tpl|")"

render_body_limit() {
    NOTIFYHUB_HARD_MAX_BODY_BYTES="$1" nginx_render_conf
    sed -n 's/^[[:space:]]*client_max_body_size[[:space:]]*\([^;]*\);.*/\1/p' "${RUN_DIR}/nginx.conf"
}

limit="$(render_body_limit 1048576)"
check "nginx: 1 MiB esatto renderizzato in byte" [ "${limit}" = "1048576" ]

limit="$(render_body_limit 1572864)"
check "nginx: 1.5 MiB non viene arrotondato per difetto (1572864 byte)" [ "${limit}" = "1572864" ]

limit="$(render_body_limit 524288)"
check "nginx: sotto 1 MiB il limite resta quello del backend (524288 byte)" [ "${limit}" = "524288" ]

limit="$(render_body_limit 20971520)"
check "nginx: default di 20 MiB invariato" [ "${limit}" = "20971520" ]

summary
