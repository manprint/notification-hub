#!/bin/bash
# notifyhub-run.sh — esegue un comando e ne invia l'output a NotifyHub.
#
# Uso tipico in crontab, al posto della chiamata diretta allo script:
#
#   0 3 * * *  /opt/notifyhub-run.sh -s SLUG -- /usr/local/bin/backup.sh /dati
#
# L'esito del comando viaggia come dato strutturato, non come testo da
# interpretare: ogni invio porta l'header
#
#   X-Exit-Code: <exit code del comando>
#
# Che cosa farne lo decide il server, con la politica configurata sul receiver
# (campo "Severity per exit code diverso da zero", default `critical`). La
# catena completa e':
#
#   1. severity esplicita   ->  solo se la forzi con --severity/--severity-*
#   2. exit code != 0       ->  politica del receiver (default: critical)
#   3. regole del receiver  ->  match sul contenuto INTERO del messaggio
#   4. severity di default del receiver
#
# Il risultato pratico non cambia rispetto a una severity cablata nello script
# ("comando fallito = critical"), ma la politica si modifica dalla dashboard
# invece che sul crontab di ogni macchina.
#
# Lo script termina SEMPRE con l'exit code del comando eseguito, cosi' cron,
# systemd o il chiamante vedono l'esito reale e non quello dell'invio.

set -uo pipefail

VERSION="1.1.0"

URL="${NOTIFYHUB_URL:-http://localhost}"
SLUG="${NOTIFYHUB_SLUG:-}"
JOB_NAME=""
SEVERITY_FORCED=""
SEVERITY_OK="${NOTIFYHUB_SEVERITY_OK:-}"
SEVERITY_FAIL="${NOTIFYHUB_SEVERITY_FAIL:-}"
ONLY_ON_FAILURE=0
TIMEOUT=""
MAX_BYTES="${NOTIFYHUB_MAX_BYTES:-1000000}"
CONNECT_TIMEOUT=10
DRY_RUN=0
QUIET=0
STRICT=0

usage() {
    cat <<'USAGE'
notifyhub-run.sh — esegue un comando e invia il suo output a NotifyHub.

  notifyhub-run.sh [OPZIONI] -- COMANDO [ARGOMENTI...]

Opzioni:
  -u, --url URL          URL base di NotifyHub          (env NOTIFYHUB_URL, default http://localhost)
  -s, --slug SLUG        Slug del receiver              (env NOTIFYHUB_SLUG) [obbligatorio]
  -n, --name NOME        Nome del job nell'intestazione (default: nome del comando)
      --severity SEV     Forza la severity in ogni caso, successo o fallimento.
                         Scavalca sia la politica sull'exit code sia le regole.
      --severity-ok SEV  Forza la severity quando exit code = 0
      --severity-fail SEV  Forza la severity quando exit code != 0
                         (default: nessuna, decide il server dalla politica del
                         receiver sull'exit code)
      --only-on-failure  Invia solo se il comando fallisce
      --timeout SEC      Uccide il comando dopo SEC secondi (exit code 124 -> fallimento)
      --max-bytes N      Tronca il corpo a N byte (default 1000000)
      --connect-timeout SEC  Timeout della chiamata HTTP (default 10)
      --strict           Esce con 1 se l'invio a NotifyHub fallisce
                         (default: l'invio fallito e' solo un avviso su stderr)
      --dry-run          Stampa il messaggio invece di inviarlo
  -q, --quiet            Non ristampa l'output del comando su stdout
  -h, --help             Questo aiuto
  -V, --version          Versione

Severity valide: debug, info, warning, error, critical.

Esempi:
  notifyhub-run.sh -s Kj8mQ2xN7vB4pR9wLs3tYc -- /usr/local/bin/backup.sh
  notifyhub-run.sh -s SLUG -n "backup notturno" --timeout 3600 -- rsync -a /dati /backup
  notifyhub-run.sh -s SLUG --only-on-failure -- systemctl is-active nginx
  NOTIFYHUB_SLUG=SLUG notifyhub-run.sh -- ./check_disco.sh
USAGE
}

die() {
    echo "notifyhub-run: $1" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        -u|--url) URL="${2:-}"; shift 2 ;;
        -s|--slug) SLUG="${2:-}"; shift 2 ;;
        -n|--name) JOB_NAME="${2:-}"; shift 2 ;;
        --severity) SEVERITY_FORCED="${2:-}"; shift 2 ;;
        --severity-ok) SEVERITY_OK="${2:-}"; shift 2 ;;
        --severity-fail) SEVERITY_FAIL="${2:-}"; shift 2 ;;
        --only-on-failure) ONLY_ON_FAILURE=1; shift ;;
        --timeout) TIMEOUT="${2:-}"; shift 2 ;;
        --max-bytes) MAX_BYTES="${2:-}"; shift 2 ;;
        --connect-timeout) CONNECT_TIMEOUT="${2:-}"; shift 2 ;;
        --strict) STRICT=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -q|--quiet) QUIET=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -V|--version) echo "notifyhub-run.sh $VERSION"; exit 0 ;;
        --) shift; break ;;
        -*) die "opzione sconosciuta: $1 (usa --help)" ;;
        *) break ;;
    esac
done

[ $# -gt 0 ] || die "nessun comando da eseguire (usa -- comando [argomenti...])"
[ -n "$SLUG" ] || die "slug del receiver mancante (-s SLUG oppure NOTIFYHUB_SLUG)"
command -v curl >/dev/null 2>&1 || die "curl non trovato nel PATH"

URL="${URL%/}"
[ -n "$JOB_NAME" ] || JOB_NAME="$(basename -- "$1")"

valid_severity() {
    case "$1" in
        debug|info|warning|error|critical) return 0 ;;
        *) return 1 ;;
    esac
}
for sev in "$SEVERITY_FORCED" "$SEVERITY_OK" "$SEVERITY_FAIL"; do
    [ -z "$sev" ] || valid_severity "$sev" || die "severity non valida: '$sev'"
done

if [ -n "$TIMEOUT" ]; then
    command -v timeout >/dev/null 2>&1 || die "--timeout richiede il comando 'timeout' (coreutils)"
fi

# --- esecuzione del comando ------------------------------------------------
# stdout e stderr uniti: chi legge la notifica vuole il log completo nell'ordine
# in cui e' stato prodotto, non due flussi separati.

COMMAND_LINE="$*"
started_at="$(date -Is 2>/dev/null || date)"
start_seconds=$SECONDS

if [ -n "$TIMEOUT" ]; then
    output="$(timeout "$TIMEOUT" "$@" 2>&1)"
    rc=$?
else
    output="$("$@" 2>&1)"
    rc=$?
fi

duration=$((SECONDS - start_seconds))

[ "$QUIET" -eq 1 ] || [ -z "$output" ] || printf '%s\n' "$output"

if [ "$ONLY_ON_FAILURE" -eq 1 ] && [ "$rc" -eq 0 ]; then
    exit 0
fi

# --- scelta della severity -------------------------------------------------
# Per default nessuna severity esplicita: l'exit code viaggia nel suo header e
# la politica la applica il server. Una severity qui compare solo se e' stata
# chiesta esplicitamente sulla riga di comando.

if [ -n "$SEVERITY_FORCED" ]; then
    severity="$SEVERITY_FORCED"
elif [ "$rc" -ne 0 ]; then
    severity="$SEVERITY_FAIL"
else
    severity="$SEVERITY_OK"
fi

if [ "$rc" -eq 0 ]; then
    esito="ok"
elif [ "$rc" -eq 124 ] && [ -n "$TIMEOUT" ]; then
    esito="timeout"
elif [ "$rc" -eq 127 ]; then
    esito="comando-non-trovato"
else
    esito="errore"
fi

# --- costruzione del corpo -------------------------------------------------
# L'intestazione resta in cima per leggibilita': le regole del server esaminano
# il contenuto per intero, quindi non c'e' nessuna finestra da rispettare e
# nessun bisogno di replicare la coda del log piu' su.

header="[notifyhub] job=${JOB_NAME} esito=${esito} exit=${rc} durata=${duration}s host=$(hostname 2>/dev/null || echo sconosciuto) avvio=${started_at}
[notifyhub] comando: ${COMMAND_LINE}"

output_bytes=$(printf '%s' "$output" | wc -c)

if [ "$output_bytes" -eq 0 ]; then
    body="${header}
[notifyhub] il comando non ha prodotto output."
else
    shown="$output"
    if [ "$output_bytes" -gt "$MAX_BYTES" ]; then
        # L'unico taglio che resta e' quello dimensionale: il receiver rifiuta
        # con 413 i corpi oltre il proprio max_body_bytes. Si tengono testa e
        # coda, che sono le parti che spiegano cos'e' successo.
        half=$((MAX_BYTES / 2))
        dropped=$((output_bytes - MAX_BYTES))
        shown="$(printf '%s' "$output" | head -c "$half")
[notifyhub] ... ${dropped} byte omessi ...
$(printf '%s' "$output" | tail -c "$half")"
    fi

    body="${header}
[notifyhub] output (${output_bytes} byte):
${shown}"
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "--- POST ${URL}/ingest/${SLUG}"
    echo "--- X-Exit-Code: ${rc}"
    echo "--- X-Severity: ${severity:-(nessuna: decide il server)}"
    echo "---"
    printf '%s\n' "$body"
    exit "$rc"
fi

# --- invio -----------------------------------------------------------------

request_id="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$$-$(date +%s)")"

curl_args=(
    --silent --show-error
    --connect-timeout "$CONNECT_TIMEOUT"
    --max-time $((CONNECT_TIMEOUT * 3))
    --write-out '\n%{http_code}'
    --request POST
    --header 'Content-Type: text/plain; charset=utf-8'
    --header "X-Request-Id: ${request_id}"
    --header "X-Exit-Code: ${rc}"
    --data-binary @-
)
[ -z "$severity" ] || curl_args+=(--header "X-Severity: ${severity}")

response="$(printf '%s' "$body" | curl "${curl_args[@]}" "${URL}/ingest/${SLUG}" 2>&1)"
curl_rc=$?
http_code="$(printf '%s' "$response" | tail -n 1)"

if [ "$curl_rc" -ne 0 ] || [ "${http_code:0:1}" != "2" ]; then
    echo "notifyhub-run: invio fallito (curl=${curl_rc} http=${http_code:-nessuno})" >&2
    printf '%s\n' "$response" | head -n -1 >&2
    [ "$STRICT" -eq 0 ] || exit 1
elif [ "$QUIET" -eq 0 ]; then
    echo "notifyhub-run: notifica inviata (http ${http_code}, severity ${severity:-decisa dal server})"
fi

# L'exit code del comando avvolto e' l'unico che conta per chi ci ha chiamati.
exit "$rc"
