#!/usr/bin/env bash
# Test di notifyhub-backup in sandbox: archivio di configurazione, rotazione.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=helpers.sh
. "${HERE}/helpers.sh"

sandbox_new
trap sandbox_clean EXIT
copy_script notifyhub-backup

BACKUP="${SANDBOX}/scripts/notifyhub-backup"
OUT="${SANDBOX}/out"
mkdir -p "${SANDBOX}/data/config"
printf 'NOTIFYHUB_SECRET_KEY=abc123\n' > "${SANDBOX}/data/config/secrets.env"

# --- archivio di configurazione che fallisce: il backup deve fallire -------
mkdir -p "${SANDBOX}/failbin"
cat > "${SANDBOX}/failbin/tar" <<'STUB'
#!/bin/bash
echo "tar: scrittura fallita" >&2
exit 1
STUB
chmod +x "${SANDBOX}/failbin/tar"

PATH="${SANDBOX}/failbin:${PATH}" "${BACKUP}" --output "${OUT}" --label fail >/dev/null 2>&1
rc=$?
check "tar fallito: notifyhub-backup esce con errore" [ "${rc}" -ne 0 ]
check "tar fallito: nessun manifest scritto" none "${OUT}/*.manifest"
check "tar fallito: nessun archivio di configurazione" none "${OUT}/*.config.tar.gz"
check "tar fallito: il dump orfano non resta in rotazione" none "${OUT}/*.sql.gz"
rm -rf "${OUT}"

# --- caso buono: archivio con secrets.env, manifest che lo cita ------------
"${BACKUP}" --output "${OUT}" --label good >/dev/null 2>&1
check "backup riuscito: esito zero" [ "$?" -eq 0 ]
ARCH="$(ls "${OUT}"/notifyhub-good-*.config.tar.gz 2>/dev/null | head -n1)"
check "backup riuscito: archivio di configurazione presente" [ -n "${ARCH}" ]
check "backup riuscito: archivio contiene config/secrets.env" \
    bash -c "tar -tzf '${ARCH}' | grep -qx 'config/secrets.env'"
MANIFEST="$(ls "${OUT}"/notifyhub-good-*.manifest 2>/dev/null | head -n1)"
check "backup riuscito: manifest cita l'archivio" grep -q "^config=${ARCH}$" "${MANIFEST}"
rm -rf "${OUT}"

# --- rotazione: il pre-aggiornamento non esce con i backup manuali ---------
# Set pre-aggiornamento con mtime vecchissimo, poi piu' backup manuali di KEEP.
"${BACKUP}" --output "${OUT}" --label pre-2.0.0 >/dev/null 2>&1
touch -d '2020-01-01' "${OUT}"/notifyhub-pre-2.0.0-*.sql.gz \
    "${OUT}"/notifyhub-pre-2.0.0-*.config.tar.gz "${OUT}"/notifyhub-pre-2.0.0-*.manifest
for n in 1 2 3 4 5 6; do
    "${BACKUP}" --output "${OUT}" --label "manual-${n}" --keep 5 >/dev/null 2>&1
done
check "rotazione: il backup pre-aggiornamento sopravvive" \
    bash -c "ls '${OUT}'/notifyhub-pre-2.0.0-*.sql.gz >/dev/null 2>&1"
check "rotazione: restano KEEP backup manuali" \
    bash -c "[ \$(ls '${OUT}'/notifyhub-manual-*.sql.gz | wc -l) -eq 5 ]"
rm -rf "${OUT}"

summary
