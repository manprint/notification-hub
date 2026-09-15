#!/usr/bin/env bash
# Funzioni comuni ai comandi dell'immagine all-in-one di NotifyHub.
# Da sorgere, non da eseguire.

NOTIFYHUB_HOME="${NOTIFYHUB_HOME:-/opt/notifyhub}"
DATA_DIR="${NOTIFYHUB_DATA_DIR:-/data}"
LOG_DIR="${NOTIFYHUB_LOG_DIR:-/logs}"
RUN_DIR=/run/notifyhub

PG_MAJOR="${PG_MAJOR:-17}"
PG_BIN="/usr/lib/postgresql/${PG_MAJOR}/bin"
PGDATA="${DATA_DIR}/postgres"
PG_SOCKET_DIR=/var/run/postgresql

CONFIG_DIR="${DATA_DIR}/config"
STATE_DIR="${DATA_DIR}/state"
BACKUP_DIR="${DATA_DIR}/backups"
MINIO_DIR="${DATA_DIR}/minio"
REDIS_DIR="${DATA_DIR}/redis"

SECRETS_FILE="${CONFIG_DIR}/secrets.env"
OVERRIDES_FILE="${CONFIG_DIR}/overrides.env"
VERSION_FILE="${STATE_DIR}/version"

APP_USER=notifyhub
APP_GROUP=notifyhub
APP_DIR="${NOTIFYHUB_HOME}/app"
VENV_BIN="${NOTIFYHUB_HOME}/venv/bin"

IMAGE_VERSION="$(cat "${NOTIFYHUB_HOME}/VERSION" 2>/dev/null || echo 0.0.0)"

# I servizi ascoltano solo su loopback: l'unico ingresso dal mondo e' nginx.
PGHOST_LOCAL=127.0.0.1
PGPORT_LOCAL=5432
REDIS_HOST_LOCAL=127.0.0.1
REDIS_PORT_LOCAL=6379
MINIO_HOST_LOCAL=127.0.0.1
MINIO_PORT_LOCAL=9000
API_PORT_LOCAL=8000
METRICS_PORT_LOCAL=9100

# ---------------------------------------------------------------------------
# log
#
# log_setup dirotta stdout e stderr dello script (e quindi di tutti i comandi
# che ci girano dentro) dentro notifyhub-logpipe: da li' ogni riga esce sia su
# stdout con il prefisso "[servizio] - " sia su /logs/<servizio>/<servizio>.log
# nella forma originale. Cosi' anche l'output di initdb, alembic o mc finisce
# nel posto giusto senza doverlo incanalare comando per comando.
# ---------------------------------------------------------------------------
NOTIFYHUB_LOG_TAG="${NOTIFYHUB_LOG_TAG:-init}"

log_setup() {
    NOTIFYHUB_LOG_TAG="${1:-${NOTIFYHUB_LOG_TAG}}"
    # Gia' incanalato dal processo chiamante: non aggiungere un secondo strato,
    # altrimenti le righe uscirebbero con il prefisso doppio.
    if [ -n "${NOTIFYHUB_LOG_WRAPPED:-}" ]; then
        return 0
    fi
    mkdir -p "${LOG_DIR}/${NOTIFYHUB_LOG_TAG}" 2>/dev/null || true
    export NOTIFYHUB_LOG_WRAPPED=1
    exec 3>&1 4>&2
    exec > >(exec /usr/local/bin/notifyhub-logpipe "${NOTIFYHUB_LOG_TAG}") 2>&1
}

# Ripristina gli fd originali: serve prima di passare il controllo a
# supervisord, che ha un suo instradamento per ogni servizio.
log_restore() {
    [ -n "${NOTIFYHUB_LOG_WRAPPED:-}" ] || return 0
    exec 1>&3 2>&4
    exec 3>&- 4>&-
    unset NOTIFYHUB_LOG_WRAPPED
}

_log() {
    local level="$1"; shift
    printf '%s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${level}" "$*"
}

log_info()  { _log INFO  "$@"; }
log_warn()  { _log WARN  "$@"; }
log_error() { _log ERROR "$@" >&2; }

die() {
    log_error "$@"
    # Segnala al trap ERR che l'errore e' gia' stato spiegato.
    NOTIFYHUB_FATAL=1
    exit 1
}

# ---------------------------------------------------------------------------
# utilita'
# ---------------------------------------------------------------------------

# Segreto esadecimale: nessun carattere da percent-encodare nelle URL.
gen_secret() {
    local bytes="${1:-32}"
    "${VENV_BIN}/python" -c "import secrets,sys; sys.stdout.write(secrets.token_hex(${bytes}))"
}

# Percent-encoding della sola userinfo delle URL: le password fornite
# dall'utente possono contenere @ : / e romperebbero la URL SQLAlchemy.
url_encode() {
    "${VENV_BIN}/python" -c "import sys,urllib.parse; sys.stdout.write(urllib.parse.quote(sys.argv[1], safe=''))" "$1"
}

# Letterale SQL con apici raddoppiati.
sql_lit() {
    printf "'%s'" "${1//\'/\'\'}"
}

# Versione senza il prefisso 'v' dei tag git. Le immagini pubblicate nascono da
# un tag e portano APP_VERSION=v0.0.3; quelle costruite in locale col Makefile
# portano 0.0.3. Confrontando le due alla lettera, `sort -V` mette le cifre
# prima delle lettere e l'aggiornamento v0.0.2 -> 0.0.3 verrebbe letto come un
# downgrade: l'avvio si fermerebbe su un'installazione perfettamente sana.
version_normalize() {
    printf '%s' "${1#v}"
}

# Uguaglianza di versione, indipendente dal prefisso.
version_eq() {
    [ "$(version_normalize "$1")" = "$(version_normalize "$2")" ]
}

# Confronto semantico di versione: ritorna 0 se $1 < $2.
version_lt() {
    local a b
    a="$(version_normalize "$1")"
    b="$(version_normalize "$2")"
    [ "$a" != "$b" ] && [ "$(printf '%s\n%s\n' "$a" "$b" | sort -V | head -n1)" = "$a" ]
}

# chown ricorsivo solo se serve davvero: su /data grosso e' l'unica differenza
# fra un riavvio in due secondi e uno in due minuti.
ensure_owner() {
    local path="$1" owner="$2" mode="${3:-}"
    mkdir -p "${path}"
    if [ "$(stat -c '%U:%G' "${path}")" != "${owner}" ]; then
        chown -R "${owner}" "${path}"
    fi
    if [ -n "${mode}" ]; then
        chmod "${mode}" "${path}"
    fi
}

wait_for_port_free() {
    local host="$1" port="$2" timeout="${3:-30}"
    local waited=0
    while "${VENV_BIN}/python" - "$host" "$port" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((sys.argv[1], int(sys.argv[2])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
    do
        waited=$((waited + 1))
        if [ "${waited}" -ge "${timeout}" ]; then
            return 1
        fi
        sleep 1
    done
    return 0
}

wait_for_tcp() {
    local host="$1" port="$2" timeout="${3:-60}" label="${4:-${host}:${port}}"
    local waited=0
    while ! "${VENV_BIN}/python" - "$host" "$port" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect((sys.argv[1], int(sys.argv[2])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
    do
        waited=$((waited + 1))
        if [ "${waited}" -ge "${timeout}" ]; then
            return 1
        fi
        sleep 1
    done
    return 0
}

# Esegue un comando come utente applicativo, dentro la directory del backend.
as_app() {
    gosu "${APP_USER}:${APP_GROUP}" "$@"
}

as_postgres() {
    gosu postgres "$@"
}

psql_super() {
    as_postgres "${PG_BIN}/psql" -v ON_ERROR_STOP=1 --no-psqlrc \
        -h "${PG_SOCKET_DIR}" -U postgres -d "${1:-postgres}" "${@:2}"
}

# ---------------------------------------------------------------------------
# segreti
#
# Precedenza: variabile d'ambiente > valore gia' persistito in
# /data/config/secrets.env > generazione. Persistere e' obbligatorio: le
# password dei ruoli PostgreSQL devono restare le stesse fra un riavvio e
# l'altro, altrimenti il cluster esistente non sarebbe piu' raggiungibile.
# ---------------------------------------------------------------------------
SECRET_VARS=(
    NOTIFYHUB_SECRET_KEY
    POSTGRES_SUPERUSER_PASSWORD
    PG_OWNER_PASSWORD
    PG_APP_PASSWORD
    PG_AUTH_PASSWORD
    PG_INGEST_PASSWORD
    NOTIFYHUB_S3_ACCESS_KEY
    NOTIFYHUB_S3_SECRET_KEY
)

# load_secrets [readonly]
#   (default)  genera i segreti mancanti e li persiste: e' l'avvio del container
#   readonly   si limita a leggere quelli esistenti, per i comandi di
#              manutenzione lanciati con docker exec su un'istanza gia' avviata
load_secrets() {
    local mode="${1:-persist}"
    local key value line

    if [ -f "${SECRETS_FILE}" ]; then
        while IFS= read -r line || [ -n "${line}" ]; do
            case "${line}" in ''|'#'*) continue ;; esac
            key="${line%%=*}"
            value="${line#*=}"
            case "${key}" in [A-Za-z_]*) ;; *) continue ;; esac
            if [ -z "${!key:-}" ]; then
                export "${key}=${value}"
            fi
        done < "${SECRETS_FILE}"
    fi

    local generated=0
    for key in "${SECRET_VARS[@]}"; do
        if [ -z "${!key:-}" ]; then
            if [ "${mode}" = "readonly" ]; then
                die "${key} non e' definita ne' in ${SECRETS_FILE}: l'istanza non e' inizializzata"
            fi
            export "${key}=$(gen_secret 24)"
            generated=1
        fi
    done

    if [ "${mode}" = "readonly" ]; then
        if [ -f "${OVERRIDES_FILE}" ]; then
            set -a
            # shellcheck disable=SC1090
            . "${OVERRIDES_FILE}"
            set +a
        fi
        return 0
    fi

    umask 077
    {
        echo "# NotifyHub - segreti generati automaticamente."
        echo "# Precedenza alle variabili d'ambiente: cambiarle qui ha effetto solo"
        echo "# se la corrispondente variabile non e' impostata sul container."
        for key in "${SECRET_VARS[@]}"; do
            printf '%s=%s\n' "${key}" "${!key}"
        done
    } > "${SECRETS_FILE}.tmp"
    mv "${SECRETS_FILE}.tmp" "${SECRETS_FILE}"
    chmod 0600 "${SECRETS_FILE}"
    umask 022

    [ "${generated}" = "1" ] && log_info "segreti mancanti generati e salvati in ${SECRETS_FILE}"

    # Override liberi dell'operatore, applicati dopo i segreti.
    if [ -f "${OVERRIDES_FILE}" ]; then
        log_info "carico override da ${OVERRIDES_FILE}"
        set -a
        # shellcheck disable=SC1090
        . "${OVERRIDES_FILE}"
        set +a
    fi
    return 0
}

# ---------------------------------------------------------------------------
# ambiente applicativo
# ---------------------------------------------------------------------------
export_runtime_env() {
    NOTIFYHUB_DB_NAME="${NOTIFYHUB_DB_NAME:-notifyhub}"
    export NOTIFYHUB_DB_NAME

    # alembic/env.py e pydantic-settings leggono un dotenv se esiste: qui la
    # configurazione arriva solo dall'ambiente, quindi il file non deve esistere.
    export ENV_FILE="${NOTIFYHUB_HOME}/no-dotenv.env"

    local owner_pw app_pw auth_pw ingest_pw
    owner_pw="$(url_encode "${PG_OWNER_PASSWORD}")"
    app_pw="$(url_encode "${PG_APP_PASSWORD}")"
    auth_pw="$(url_encode "${PG_AUTH_PASSWORD}")"
    ingest_pw="$(url_encode "${PG_INGEST_PASSWORD}")"

    local host="${PGHOST_LOCAL}:${PGPORT_LOCAL}/${NOTIFYHUB_DB_NAME}"
    export DATABASE_URL_OWNER="postgresql+asyncpg://notifyhub_owner:${owner_pw}@${host}"
    export DATABASE_URL_APP="postgresql+asyncpg://notifyhub_app:${app_pw}@${host}"
    export DATABASE_URL_AUTH="postgresql+asyncpg://notifyhub_auth:${auth_pw}@${host}"
    export DATABASE_URL_INGEST="postgresql+asyncpg://notifyhub_ingest:${ingest_pw}@${host}"
    export DATABASE_URL_SYNC="postgresql+psycopg://notifyhub_app:${app_pw}@${host}"

    export REDIS_URL="redis://${REDIS_HOST_LOCAL}:${REDIS_PORT_LOCAL}/0"
    export CELERY_BROKER_URL="redis://${REDIS_HOST_LOCAL}:${REDIS_PORT_LOCAL}/1"

    export NOTIFYHUB_S3_ENDPOINT="http://${MINIO_HOST_LOCAL}:${MINIO_PORT_LOCAL}"
    export NOTIFYHUB_S3_BUCKET="${NOTIFYHUB_S3_BUCKET:-notifyhub-payloads}"
    export NOTIFYHUB_S3_REGION="${NOTIFYHUB_S3_REGION:-us-east-1}"

    export MINIO_ROOT_USER="${NOTIFYHUB_S3_ACCESS_KEY}"
    export MINIO_ROOT_PASSWORD="${NOTIFYHUB_S3_SECRET_KEY}"
    export MINIO_UPDATE=off
    export MINIO_BROWSER="${MINIO_BROWSER:-off}"
    export MC_CONFIG_DIR="${RUN_DIR}/mc"

    # Impostazioni applicative con default sensati per il container unico.
    export NOTIFYHUB_PUBLIC_BASE_URL="${NOTIFYHUB_PUBLIC_BASE_URL:-http://localhost}"
    export NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST="${NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST:-hooks.slack.com,chat.googleapis.com}"
    export NOTIFYHUB_INLINE_MAX_BYTES="${NOTIFYHUB_INLINE_MAX_BYTES:-1048576}"
    export NOTIFYHUB_HARD_MAX_BODY_BYTES="${NOTIFYHUB_HARD_MAX_BODY_BYTES:-20971520}"
    export ALLOW_PUBLIC_REGISTRATION="${ALLOW_PUBLIC_REGISTRATION:-false}"
    export ACCESS_TOKEN_TTL_MINUTES="${ACCESS_TOKEN_TTL_MINUTES:-15}"
    export REFRESH_TOKEN_TTL_DAYS="${REFRESH_TOKEN_TTL_DAYS:-30}"
    # SPA e API sono sulla stessa origine dietro nginx: nessun CORS necessario.
    export CORS_ORIGINS="${CORS_ORIGINS:-}"
    export TRUSTED_PROXIES="${TRUSTED_PROXIES:-}"
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"

    # Parametri di esecuzione dei servizi, letti da supervisord.conf.
    export WORKER_CONCURRENCY="${WORKER_CONCURRENCY:-4}"
    export UVICORN_WORKERS="${UVICORN_WORKERS:-2}"
    export METRICS_BIND="${METRICS_BIND:-127.0.0.1}"
    export MINIO_BIND="${MINIO_BIND:-127.0.0.1}"
    export LOG_MAX_BYTES="${LOG_MAX_BYTES:-10485760}"
    export LOG_BACKUPS="${LOG_BACKUPS:-5}"
    export TZ="${TZ:-UTC}"
}
