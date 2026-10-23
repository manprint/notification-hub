#!/usr/bin/env bash
# Test di notifyhub-restore in sandbox: chiave dall'archivio di configurazione,
# supervisord in stato degradato, errori SQL, round trip backup -> restore.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=helpers.sh
. "${HERE}/helpers.sh"

sandbox_new
trap sandbox_clean EXIT
copy_script notifyhub-backup
copy_script notifyhub-restore

BACKUP="${SANDBOX}/scripts/notifyhub-backup"
RESTORE="${SANDBOX}/scripts/notifyhub-restore"
OUT="${SANDBOX}/out"
K0="chiave-del-backup"
K1="chiave-della-nuova-istanza"
SECRETS="${SANDBOX}/data/config/secrets.env"

mkdir -p "${SANDBOX}/data/config"
write_secrets() {
    cat > "${SECRETS}" <<EOF
NOTIFYHUB_SECRET_KEY=$1
POSTGRES_SUPERUSER_PASSWORD=pw-superuser
PG_OWNER_PASSWORD=pw-owner
PG_APP_PASSWORD=pw-app
PG_AUTH_PASSWORD=pw-auth
PG_INGEST_PASSWORD=pw-ingest
NOTIFYHUB_S3_ACCESS_KEY=s3-access
NOTIFYHUB_S3_SECRET_KEY=s3-secret
EOF
}

# Backup dell'istanza originale: il dump e l'archivio portano K0.
write_secrets "${K0}"
"${BACKUP}" --output "${OUT}" --label t >/dev/null 2>&1
DUMP="$(ls "${OUT}"/notifyhub-t-*.sql.gz | head -n1)"
ARCH="${DUMP%.sql.gz}.config.tar.gz"

# Ogni caso parte da una nuova istanza con K1 e nessun effetto precedente.
reset_case() {
    rm -f "${SANDBOX}/psql-input.sql" "${SANDBOX}/supervisor.calls"
    write_secrets "${K1}"
    unset NOTIFYHUB_SECRET_KEY STUB_PSQL_STDERR STUB_PSQL_RC STUB_SUPERVISOR_UP
}

secret_in() {
    grep -m1 '^NOTIFYHUB_SECRET_KEY=' "$1" | cut -d= -f2-
}

secret_is() {
    [ "$(secret_in "$1")" = "$2" ]
}

# --- supervisord con un programma FATAL: i servizi devono fermarsi comunque --
reset_case
"${RESTORE}" "${DUMP}" --yes >/dev/null 2>&1
check "supervisord degradato: servizi fermati prima del ripristino" \
    grep -q ' stop nginx api metrics worker beat$' "${SANDBOX}/supervisor.calls"
check "supervisord degradato: servizi riavviati dopo il ripristino" \
    grep -q ' start nginx api metrics worker beat$' "${SANDBOX}/supervisor.calls"

# --- errore SQL inatteso: il ripristino non deve dichiararsi riuscito --------
reset_case
STUB_PSQL_STDERR='ERROR:  relation "t_demo" already exists' \
    "${RESTORE}" "${DUMP}" --yes > "${SANDBOX}/restore.out" 2>&1
check "errore SQL inatteso: esito non zero" [ "$?" -ne 0 ]
check "errore SQL inatteso: niente messaggio di successo" \
    bash -c "! grep -q 'ripristino completato' '${SANDBOX}/restore.out'"

# Gli errori attesi di pg_dumpall --clean sul cluster vivo non bloccano.
reset_case
STUB_PSQL_STDERR='ERROR:  current user cannot be dropped' \
    "${RESTORE}" "${DUMP}" --yes >/dev/null 2>&1
check "errore atteso di --clean (ruolo corrente): esito zero" [ "$?" -eq 0 ]

# --- archivio di configurazione: la chiave del backup torna in secrets.env ---
reset_case
"${RESTORE}" "${DUMP}" --yes > "${SANDBOX}/restore.out" 2>&1
check "istanza nuova: la chiave in secrets.env e' quella del backup" secret_is "${SECRETS}" "${K0}"
check "istanza nuova: le altre credenziali restano quelle dell'istanza" \
    grep -q '^NOTIFYHUB_S3_ACCESS_KEY=s3-access$' "${SECRETS}"
check "istanza nuova: il ripristino avvisa che serve un riavvio" \
    grep -q 'riavviare il container' "${SANDBOX}/restore.out"

# Archivio assente: si rifiuta prima di toccare il database.
reset_case
mv "${ARCH}" "${SANDBOX}/archivio.da-parte"
"${RESTORE}" "${DUMP}" --yes >/dev/null 2>&1
check "archivio assente: ripristino rifiutato" [ "$?" -ne 0 ]
check "archivio assente: il database non viene toccato" [ ! -f "${SANDBOX}/psql-input.sql" ]
check "archivio assente: i servizi non vengono fermati" [ ! -f "${SANDBOX}/supervisor.calls" ]
check "archivio assente: la chiave locale resta invariata" secret_is "${SECRETS}" "${K1}"
mv "${SANDBOX}/archivio.da-parte" "${ARCH}"

# Con --senza-configurazione il rischio e' accettato esplicitamente.
reset_case
mv "${ARCH}" "${SANDBOX}/archivio.da-parte"
"${RESTORE}" "${DUMP}" --yes --senza-configurazione >/dev/null 2>&1
mv "${SANDBOX}/archivio.da-parte" "${ARCH}"
check "archivio assente con --senza-configurazione: ripristino eseguito" \
    [ -f "${SANDBOX}/psql-input.sql" ]

# Archivio con una chiave diversa e NOTIFYHUB_SECRET_KEY fissata nell'ambiente
# del container: non si puo' rispettare entrambe, quindi si rifiuta.
reset_case
NOTIFYHUB_SECRET_KEY="${K1}" "${RESTORE}" "${DUMP}" --yes >/dev/null 2>&1
check "chiave fissata nell'ambiente diversa dal backup: rifiutato" [ "$?" -ne 0 ]
check "chiave fissata nell'ambiente diversa dal backup: database intatto" \
    [ ! -f "${SANDBOX}/psql-input.sql" ]

# La stessa chiave fissata in overrides.env vince su secrets.env al riavvio:
# il ripristino deve rifiutare anche in questo caso.
reset_case
OVERRIDES="${SANDBOX}/data/config/overrides.env"
printf 'NOTIFYHUB_SECRET_KEY=%s\n' "${K1}" > "${OVERRIDES}"
"${RESTORE}" "${DUMP}" --yes >/dev/null 2>&1
check "chiave fissata in overrides.env diversa dal backup: rifiutato" [ "$?" -ne 0 ]
check "chiave fissata in overrides.env diversa dal backup: database intatto" \
    [ ! -f "${SANDBOX}/psql-input.sql" ]
rm -f "${OVERRIDES}"

# --- round trip: backup su un'istanza, restore su un volume nuovo -----------
reset_case
NEW_DATA="${SANDBOX}/data-nuovo"
mkdir -p "${NEW_DATA}/config"
cat > "${NEW_DATA}/config/secrets.env" <<EOF
NOTIFYHUB_SECRET_KEY=${K1}
POSTGRES_SUPERUSER_PASSWORD=pw-nuovo
EOF
NOTIFYHUB_DATA_DIR="${NEW_DATA}" "${RESTORE}" "${DUMP}" --yes >/dev/null 2>&1
check "round trip su volume nuovo: esito zero" [ "$?" -eq 0 ]
check "round trip su volume nuovo: la chiave dei webhook e' quella del backup" \
    secret_is "${NEW_DATA}/config/secrets.env" "${K0}"

rm -rf "${OUT}"
summary
