#!/usr/bin/env bash
# Funzioni comuni ai test shell dell'immagine all-in-one. Da sorgere.
#
# Gli script di rootfs/ girano in una sandbox temporanea: lib.sh viene copiato
# con il percorso dei binari PostgreSQL spostato nella sandbox, e gosu, psql,
# pg_dumpall, pg_isready e supervisorctl sono stub. Niente di questo tocca il
# sistema: i test non richiedono Docker ne' un cluster PostgreSQL.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOTFS="${HERE}/../rootfs/usr/local"
PASSES=0
FAILS=0
SANDBOX=""

ok() { PASSES=$((PASSES + 1)); echo "ok   - $*"; }
ko() { FAILS=$((FAILS + 1)); echo "FAIL - $*"; }

# check DESCRIZIONE COMANDO...: registra esito e continua.
check() {
    local desc="$1"; shift
    if "$@"; then ok "${desc}"; else ko "${desc}"; fi
}

# none GLOB: vero se il glob non trova file.
none() {
    ! compgen -G "$1" >/dev/null
}

# none_match REGEX FILE: vero se nessuna riga del file corrisponde.
none_match() {
    ! grep -Eq "$1" "$2"
}

# Estrae una funzione da uno script senza eseguirlo (lo script chiamerebbe boot).
extract_fn() {
    local name="$1" file="$2"
    sed -n "/^${name}()/,/^}/p" "${file}"
}

sandbox_new() {
    SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/nh-test.XXXXXX")"
    mkdir -p "${SANDBOX}/bin" "${SANDBOX}/lib" "${SANDBOX}/scripts" "${SANDBOX}/pgbin" \
        "${SANDBOX}/home/venv/bin" "${SANDBOX}/data" "${SANDBOX}/logs/init"

    export NOTIFYHUB_DATA_DIR="${SANDBOX}/data"
    export NOTIFYHUB_LOG_DIR="${SANDBOX}/logs"
    export NOTIFYHUB_HOME="${SANDBOX}/home"
    # Con NOTIFYHUB_LOG_WRAPPED log_setup non avvia notifyhub-logpipe.
    export NOTIFYHUB_LOG_WRAPPED=1
    export PATH="${SANDBOX}/bin:${PATH}"
    unset NOTIFYHUB_SECRET_KEY

    sed -e "s|PG_BIN=\"/usr/lib/postgresql/\${PG_MAJOR}/bin\"|PG_BIN=\"${SANDBOX}/pgbin\"|" \
        "${ROOTFS}/lib/notifyhub/lib.sh" > "${SANDBOX}/lib/lib.sh"

    cat > "${SANDBOX}/bin/gosu" <<'STUB'
#!/bin/bash
shift
exec "$@"
STUB

    cat > "${SANDBOX}/pgbin/pg_isready" <<'STUB'
#!/bin/bash
exit 0
STUB

    cat > "${SANDBOX}/pgbin/pg_dumpall" <<STUB
#!/bin/bash
if [ "\${STUB_DUMP_FAIL:-0}" = 1 ]; then echo "pg_dumpall: errore" >&2; exit 1; fi
echo "-- dump di prova"
echo "CREATE TABLE t_demo (id int);"
STUB

    # Registra l'input SQL. Con -tAc risponde STUB_PSQL_COUNT; stampa su stderr
    # STUB_PSQL_STDERR ed esce con STUB_PSQL_RC.
    cat > "${SANDBOX}/pgbin/psql" <<STUB
#!/bin/bash
case " \$* " in
    *" -tAc "*) echo "\${STUB_PSQL_COUNT:-0}"; exit 0 ;;
esac
cat >> "${SANDBOX}/psql-input.sql"
if [ -n "\${STUB_PSQL_STDERR:-}" ]; then printf '%s\n' "\${STUB_PSQL_STDERR}" >&2; fi
exit "\${STUB_PSQL_RC:-0}"
STUB

    # Stato simulato: STUB_SUPERVISOR_UP=0 significa supervisord non raggiungibile.
    # Ogni invocazione finisce in supervisor.calls.
    cat > "${SANDBOX}/home/venv/bin/supervisorctl" <<STUB
#!/bin/bash
echo "\$*" >> "${SANDBOX}/supervisor.calls"
case "\$*" in
    *" version"*)
        if [ "\${STUB_SUPERVISOR_UP:-1}" = 1 ]; then echo 4.3.0; exit 0; fi
        echo "http://localhost refused connection"; exit 3 ;;
    *" status"*)
        # Programma FATAL: supervisorctl status esce con 3 come in 4.3.0.
        echo "nginx RUNNING"; echo "beat FATAL"; exit 3 ;;
esac
exit 0
STUB

    chmod +x "${SANDBOX}/bin/gosu" "${SANDBOX}/pgbin/"* "${SANDBOX}/home/venv/bin/supervisorctl"
}

# copy_script NOME: copia uno script di rootfs/usr/local/bin nella sandbox,
# con il percorso di lib.sh riscritto su quello della sandbox.
copy_script() {
    local name="$1"
    sed -e "s|/usr/local/lib/notifyhub/lib.sh|${SANDBOX}/lib/lib.sh|" \
        "${ROOTFS}/bin/${name}" > "${SANDBOX}/scripts/${name}"
    chmod +x "${SANDBOX}/scripts/${name}"
}

sandbox_clean() {
    if [ -n "${SANDBOX}" ] && [ -d "${SANDBOX}" ]; then
        rm -rf "${SANDBOX}"
    fi
}

summary() {
    echo "passati=${PASSES} falliti=${FAILS}"
    [ "${FAILS}" -eq 0 ]
}
