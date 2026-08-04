#!/bin/bash
# notifyhub-run.sh — esegue un comando e ne invia l'output a NotifyHub.
#
# Uso tipico in crontab, al posto della chiamata diretta allo script:
#
#   0 3 * * *  /opt/notifyhub-run.sh -s SLUG -- /usr/local/bin/backup.sh /dati
#
# Una copia con URL e slug gia' compilati si scarica dalla pagina del receiver
# nella dashboard, col pulsante "Scarica lo script": l'URL e' quella pubblica
# dell'istanza, quindi non va indovinata a mano ne' corretta a valle di un
# cambio di dominio o del passaggio a https.
#
# L'esito del comando viaggia come dato strutturato, non come testo da
# interpretare: ogni invio porta gli header
#
#   X-Exit-Code:   <exit code del comando>
#   X-Duration-Ms: <durata dell'esecuzione in millisecondi>
#
# Che cosa farne lo decide il server, con le politiche configurate sul receiver
# (campi "Severity per exit code diverso da zero", default `critical`, e "Soglia
# di durata", di partenza disattivata). La catena completa e':
#
#   1. severity esplicita   ->  solo se la forzi con --severity/--severity-*
#   2. esito dell'esecuzione:
#        - exit code != 0        -> politica del receiver (default: critical)
#        - durata oltre soglia   -> severity della soglia del receiver
#      se scattano entrambi vince la piu grave
#   3. regole del receiver  ->  match sul contenuto INTERO del messaggio
#   4. severity di default del receiver
#
# Il risultato pratico non cambia rispetto a una severity cablata nello script
# ("comando fallito = critical"), ma la politica si modifica dalla dashboard
# invece che sul crontab di ogni macchina.
#
# La durata serve al caso che nessuna regola sul contenuto sa vedere: un job che
# finisce bene, senza una riga di errore, ma in venti minuti invece dei cinque
# soliti. Lo script la misura sempre e la manda sempre; se il receiver non ha
# una soglia configurata il dato resta solo informativo (visibile in dashboard).
#
# Il caso opposto - questo script che non gira per niente, perche' la macchina e'
# spenta o il cron e' stato rimosso - non puo' vederlo nessuno da qui: nessuno
# parla. Lo copre la "sorveglianza dell'attesa" sul receiver, che dichiara ogni
# quanto un invio e' atteso e fa scrivere a NotifyHub una notifica di assenza
# quando la scadenza passa in silenzio. Con quella attiva NON usare
# --only-on-failure: un'esecuzione riuscita che non invia niente e'
# indistinguibile da una macchina spenta.
#
# Con --ping-start lo script manda anche un ping PRIMA di eseguire il comando
# (header X-Phase: start, severity debug). Serve a una distinzione che altrimenti
# il server non puo' fare: "il cron non e' partito" e "il job e' partito alle 3 ed
# e' morto a meta' backup con la macchina" arrivano entrambi come silenzio. Col
# ping di avvio la notifica di assenza dice quale dei due e'.
#
# Il ping di avvio non e' un esito: non aggiorna l'ultima conclusione vista dal
# server, e un suo fallimento e' solo un avviso su stderr. Il comando viene
# eseguito comunque, anche se NotifyHub non risponde.
#
# Lo script termina SEMPRE con l'exit code del comando eseguito, cosi' cron,
# systemd o il chiamante vedono l'esito reale e non quello dell'invio.

set -uo pipefail

VERSION="1.4.0"

# --- configurazione --------------------------------------------------------
# Le due righe qui sotto sono le uniche da toccare per mettere in funzione lo
# script, e sono anche quelle che riscrive il pulsante "Scarica lo script" nella
# pagina del receiver: da li' si ottiene una copia con URL e slug gia' dentro,
# con l'URL pubblica vera dell'istanza (reverse proxy e https compresi).
# Precedenza: opzioni -u/-s > variabili d'ambiente NOTIFYHUB_URL/NOTIFYHUB_SLUG
# > valori scritti qui.
URL="${NOTIFYHUB_URL:-http://localhost}"
SLUG="${NOTIFYHUB_SLUG:-}"

JOB_NAME=""
SEVERITY_FORCED=""
SEVERITY_OK="${NOTIFYHUB_SEVERITY_OK:-}"
SEVERITY_FAIL="${NOTIFYHUB_SEVERITY_FAIL:-}"
ONLY_ON_FAILURE=0
PING_START="${NOTIFYHUB_PING_START:-0}"
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

Ogni invio porta exit code e durata dell'esecuzione (header X-Exit-Code e
X-Duration-Ms): la severity la decide il server con le politiche del receiver,
soglia di durata compresa.

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
      --only-on-failure  Invia solo se il comando fallisce.
                         ATTENZIONE: incompatibile con la sorveglianza
                         dell'attesa configurata sul receiver, che
                         interpreterebbe ogni successo come un'assenza. In quel
                         caso invia sempre e usa --severity-ok debug.
      --ping-start       Manda un ping prima di eseguire il comando (X-Phase: start,
                         severity debug), cosi' il server distingue "non e' partito"
                         da "partito e mai concluso"  (env NOTIFYHUB_PING_START=1)
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

Dalla pagina del receiver in dashboard si scarica questo stesso script con URL e
slug gia' scritti nel blocco "configurazione" in cima al file: restano
modificabili a mano, e le opzioni -u/-s continuano a scavalcarli.

La soglia di durata non si configura qui: sta sul receiver, perche' e' una
politica ("questo backup non deve superare i 10 minuti") e non un dettaglio
della singola macchina. Lo script manda sempre la misura.

Nemmeno l'attesa si configura qui: sul receiver si dichiara ogni quanto un invio
e' atteso, e NotifyHub segnala da se' le esecuzioni che non arrivano. Con
--ping-start la segnalazione dice anche se il job non e' partito o se e' partito
e non ha concluso.
USAGE
}

die() {
    echo "notifyhub-run: $1" >&2
    exit 2
}

# --- misura del tempo ------------------------------------------------------
# Millisecondi, non secondi: e' l'unita' che si puo' misurare senza arrotondare,
# e la soglia sul receiver si configura comunque in secondi. Tre sorgenti, in
# ordine di preferenza: EPOCHREALTIME (bash >= 5, nessun processo esterno),
# `date +%s%3N` (GNU coreutils), `date +%s` (qualunque date, precisione al
# secondo). Su nessuna di queste il tempo e' monotono, quindi la differenza
# viene comunque protetta dal salto d'orologio (vedi sotto).

now_ms() {
    local stamp whole frac
    if [ -n "${EPOCHREALTIME:-}" ]; then
        whole="${EPOCHREALTIME%%[.,]*}"
        frac="${EPOCHREALTIME#*[.,]}000"
        printf '%s%s' "$whole" "${frac:0:3}"
        return
    fi
    stamp="$(date +%s%3N 2>/dev/null)" || stamp=""
    case "$stamp" in
        ''|*[!0-9]*) printf '%s000' "$(date +%s)" ;;
        *) printf '%s' "$stamp" ;;
    esac
}

# Durata leggibile da chi apre la notifica: "12m30s", non "750123ms".
human_duration() {
    local total_ms="$1" secs mins hours
    secs=$((total_ms / 1000))
    if [ "$secs" -lt 60 ]; then
        # Sotto il minuto i millisecondi contano: distinguono un comando che ha
        # lavorato per mezzo secondo da uno morto subito.
        printf '%d.%03ds' "$secs" "$((total_ms % 1000))"
        return
    fi
    hours=$((secs / 3600))
    mins=$(((secs % 3600) / 60))
    secs=$((secs % 60))
    if [ "$hours" -gt 0 ]; then
        printf '%dh%02dm%02ds' "$hours" "$mins" "$secs"
    else
        printf '%dm%02ds' "$mins" "$secs"
    fi
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
        --ping-start) PING_START=1; shift ;;
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

# "1", "true", "yes", "on": chi esporta NOTIFYHUB_PING_START=true si aspetta che
# funzioni, e un valore non riconosciuto disattivava il ping in silenzio.
case "$(printf '%s' "$PING_START" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) PING_START=1 ;;
    *) PING_START=0 ;;
esac

# I ping di avvio senza le conclusioni sono peggio di nessun ping: il server
# vedrebbe partire ogni esecuzione e concludere solo quelle fallite, cioe'
# esattamente il quadro di un job che muore a meta' ogni volta che va bene.
if [ "$PING_START" -eq 1 ] && [ "$ONLY_ON_FAILURE" -eq 1 ]; then
    echo "notifyhub-run: --ping-start con --only-on-failure segnala ogni esecuzione riuscita come interrotta a meta'; usa --severity-ok debug al posto di --only-on-failure" >&2
fi

# --- esecuzione del comando ------------------------------------------------
# stdout e stderr uniti: chi legge la notifica vuole il log completo nell'ordine
# in cui e' stato prodotto, non due flussi separati.

COMMAND_LINE="$*"
started_at="$(date -Is 2>/dev/null || date)"

# --- ping di avvio ----------------------------------------------------------
# Prima di eseguire: dice al server "questa esecuzione e' partita". Non e' un
# esito, quindi va con severity debug (nessuna regola sul contenuto deve poter
# promuovere un avvio a critical) e non conta come conclusione lato server.
# Best-effort per costruzione: se NotifyHub non risponde il job parte comunque,
# --strict compreso. Perdere un ping di avvio degrada la diagnosi, fermare il
# backup per un ping perso sarebbe un danno peggiore del guasto.

send_ping_start() {
    local body request_id
    request_id="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "$$-$(date +%s)")"
    body="[notifyhub] job=${JOB_NAME} avvio host=$(hostname 2>/dev/null || echo sconosciuto) alle=${started_at}
[notifyhub] comando: ${COMMAND_LINE}
[notifyhub] questo e' un ping di avvio: l'esito arriva a fine esecuzione."

    if [ "$DRY_RUN" -eq 1 ]; then
        echo "--- POST ${URL}/ingest/${SLUG}"
        echo "--- X-Phase: start"
        echo "--- X-Severity: debug"
        echo "---"
        printf '%s\n' "$body"
        return 0
    fi

    printf '%s' "$body" | curl \
        --silent --show-error \
        --connect-timeout "$CONNECT_TIMEOUT" \
        --max-time $((CONNECT_TIMEOUT * 3)) \
        --output /dev/null \
        --request POST \
        --header 'Content-Type: text/plain; charset=utf-8' \
        --header "X-Request-Id: ${request_id}" \
        --header 'X-Phase: start' \
        --header 'X-Severity: debug' \
        --data-binary @- \
        "${URL}/ingest/${SLUG}" \
        || echo "notifyhub-run: ping di avvio non inviato (il comando parte comunque)" >&2
    return 0
}

[ "$PING_START" != "1" ] || send_ping_start

start_ms="$(now_ms)"

if [ -n "$TIMEOUT" ]; then
    output="$(timeout "$TIMEOUT" "$@" 2>&1)"
    rc=$?
else
    output="$("$@" 2>&1)"
    rc=$?
fi

duration_ms=$(( $(now_ms) - start_ms ))
# Un orologio spostato indietro durante l'esecuzione (ntp, correzione manuale)
# darebbe una durata negativa: meglio zero che un numero che il server dovrebbe
# poi scartare.
[ "$duration_ms" -ge 0 ] || duration_ms=0
duration_human="$(human_duration "$duration_ms")"

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

header="[notifyhub] job=${JOB_NAME} esito=${esito} exit=${rc} durata=${duration_human} (${duration_ms}ms) host=$(hostname 2>/dev/null || echo sconosciuto) avvio=${started_at}
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
    echo "--- X-Phase: end"
    echo "--- X-Exit-Code: ${rc}"
    echo "--- X-Duration-Ms: ${duration_ms}"
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
    --header 'X-Phase: end'
    --header "X-Exit-Code: ${rc}"
    --header "X-Duration-Ms: ${duration_ms}"
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
