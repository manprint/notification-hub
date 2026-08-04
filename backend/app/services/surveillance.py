"""Sorveglianza dell'attesa: accorgersi di una notifica che NON e' arrivata.

Tutto il resto del sistema ragiona su messaggi che arrivano. Il guasto piu'
banale non ne produce nessuno: la macchina e' spenta, cron e' disabilitato, la
rete verso NotifyHub non c'e'. E' un dead man's switch, e per definizione puo'
viverci solo il server: dalla macchina sorvegliata, quando il guasto e' quello,
non parla piu' nessuno.

Qui c'e' il calcolo, senza database e senza Celery: dato lo stato di un receiver
e l'istante corrente, quando scade l'attesa e che cosa scrivere nella notifica.
Il job che lo usa e' `app.tasks.maintenance.check_expected_schedules`.

Due modi di dichiarare l'attesa, mai insieme:

  * intervallo fisso (`every_seconds`): "ogni 24 ore". Semplice e senza fusi.
  * espressione cron (`cron` + `timezone`): la stessa riga del crontab. Serve ai
    job non equispaziati: `0 3 * * 1-5` con un intervallo fisso di 24 ore
    darebbe un falso allarme ogni sabato.

In entrambi i casi la funzione pubblica e' una sola, `alert_deadline`: l'istante
oltre il quale l'assenza diventa un allarme. "E' in ritardo" e' `now > deadline`,
e la stessa data si mostra in dashboard come "allarme se non arriva entro...".
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from app.db.types import Severity

if TYPE_CHECKING:  # solo per l'annotazione: nessun import a runtime
    from app.models.receiver import Receiver

DEFAULT_TIMEZONE = "UTC"
CRON_FIELDS = 5  # minuto ora giorno mese giorno-settimana, come in crontab
CRON_MAX_CHARS = 100
# Oltre questo non si cerca piu' indietro: un cron valido ma che non scatta mai
# nella pratica (`0 0 30 2 *`, 30 febbraio) non deve far girare croniter a vuoto.
CRON_LOOKBACK_DAYS = 400


class InvalidScheduleError(ValueError):
    """Espressione cron o fuso orario non utilizzabili."""


@dataclass(frozen=True)
class ExpectedSchedule:
    """La politica di attesa di un receiver, gia' validata."""

    grace_seconds: int
    severity: Severity
    every_seconds: int | None = None
    cron: str | None = None
    timezone: str | None = None

    @property
    def is_cron(self) -> bool:
        return self.cron is not None


def schedule_from_receiver(receiver: "Receiver") -> ExpectedSchedule | None:
    """La politica del receiver, o None se la sorveglianza e' spenta.

    `missing_severity` e' il discriminante: il CHECK della migrazione 0012
    garantisce che, se c'e' quella, ci siano anche tolleranza e uno fra
    intervallo ed espressione cron."""
    if receiver.missing_severity is None:
        return None
    return ExpectedSchedule(
        grace_seconds=receiver.expected_grace_seconds or 0,
        severity=receiver.missing_severity,
        every_seconds=receiver.expected_every_seconds,
        cron=receiver.expected_cron,
        timezone=receiver.expected_timezone,
    )


def validate_cron(expression: str) -> str:
    """Accetta le sole espressioni a 5 campi, quelle che si scrivono in crontab.

    croniter ne accetta anche altre forme (6 campi con i secondi, `@daily`): qui
    si resta sulla sintassi che l'operatore ha davanti nel proprio crontab,
    perche' e' quella che sta confrontando con la configurazione del receiver.
    """
    candidate = expression.strip()
    if not candidate:
        raise InvalidScheduleError("l'espressione cron e' vuota")
    if len(candidate) > CRON_MAX_CHARS:
        raise InvalidScheduleError(f"l'espressione cron supera {CRON_MAX_CHARS} caratteri")
    if len(candidate.split()) != CRON_FIELDS:
        raise InvalidScheduleError(
            "l'espressione cron deve avere 5 campi (minuto ora giorno mese giorno-settimana), "
            f"come in crontab: ricevuti {len(candidate.split())}"
        )
    if not croniter.is_valid(candidate):
        raise InvalidScheduleError(f"espressione cron non valida: {candidate!r}")
    return candidate


def validate_timezone(name: str) -> str:
    candidate = name.strip()
    if not candidate:
        raise InvalidScheduleError("il fuso orario e' vuoto")
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidScheduleError(f"fuso orario sconosciuto: {candidate!r}") from exc
    return candidate


def _zone(schedule: ExpectedSchedule) -> ZoneInfo:
    return ZoneInfo(schedule.timezone or DEFAULT_TIMEZONE)


def _cron_fire_times(schedule: ExpectedSchedule, now: datetime) -> tuple[datetime, datetime]:
    """Occorrenza precedente e successiva rispetto a `now`, in UTC.

    Il conto si fa nel fuso dichiarato e non in UTC: "0 3 * * *" a Roma vuol dire
    le 3 di notte anche il giorno in cui l'ora legale sposta l'orologio.
    """
    assert schedule.cron is not None  # garantito da is_cron
    zone = _zone(schedule)
    base = now.astimezone(zone)
    iterator = croniter(schedule.cron, base)
    previous = iterator.get_prev(datetime)
    following = iterator.get_next(datetime)
    return previous.astimezone(UTC), following.astimezone(UTC)


def alert_deadline(
    schedule: ExpectedSchedule,
    *,
    reference: datetime,
    now: datetime,
) -> datetime:
    """Istante oltre il quale l'assenza e' un allarme.

    `reference` e' l'ultimo invio vero, oppure il momento in cui la politica e'
    entrata in vigore per un receiver che non ha mai ricevuto niente.

    Col cron non basta "ultima occorrenza + tolleranza": se l'invio dell'ultima
    occorrenza e' arrivato, la scadenza da mostrare (e da attendere) e' quella
    della prossima. Cosi' la stessa funzione risponde sia a "e' in ritardo?" sia
    a "entro quando lo aspetto?".
    """
    grace = timedelta(seconds=schedule.grace_seconds)
    if not schedule.is_cron:
        assert schedule.every_seconds is not None
        return reference + timedelta(seconds=schedule.every_seconds) + grace

    previous, following = _cron_fire_times(schedule, now)
    fire = previous if reference < previous else following
    return fire + grace


def is_missing(schedule: ExpectedSchedule, *, reference: datetime, now: datetime) -> bool:
    return now > alert_deadline(schedule, reference=reference, now=now)


# --- testi ------------------------------------------------------------------
# Le notifiche sintetiche sono l'unica cosa che l'operatore vede di questa
# funzione: il contenuto dice cosa si aspettava il sistema, cosa ha visto e cosa
# guardare. Prima riga autoportante, perche' nell'elenco si vede solo quella.


def format_seconds(total: int) -> str:
    """`90` -> `1m30s`, `86400` -> `24h00m`, `604800` -> `7g`."""
    if total < 60:
        return f"{total}s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}g{hours:02d}h" if hours else f"{days}g"


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def describe_expectation(schedule: ExpectedSchedule) -> str:
    tolerance = format_seconds(schedule.grace_seconds)
    if schedule.is_cron:
        zone = schedule.timezone or DEFAULT_TIMEZONE
        return f"cron `{schedule.cron}` ({zone}), tolleranza {tolerance}"
    assert schedule.every_seconds is not None
    return f"ogni {format_seconds(schedule.every_seconds)}, tolleranza {tolerance}"


def diagnose_phase(
    *,
    last_start_at: datetime | None,
    last_notification_at: datetime | None,
    now: datetime,
) -> str:
    """Quale dei due guasti si sta segnalando: "non e' partito" o "e' partito e
    non ha mai finito".

    Senza i ping di avvio (`--ping-start` del wrapper) i due casi sono
    indistinguibili dal server, e la riga lo dice invece di tacere: sapere che il
    dato manca e' meglio che credere di saperlo.
    """
    if last_start_at is None:
        return (
            "[notifyhub] non e' possibile dire se l'esecuzione non e' partita o se e' "
            "partita e si e' interrotta: questo receiver non riceve ping di avvio "
            "(wrapper con --ping-start)."
        )

    concluso_dopo = last_notification_at is not None and last_notification_at >= last_start_at
    if concluso_dopo:
        return (
            f"[notifyhub] l'ultima esecuzione partita ({_stamp(last_start_at)}) aveva "
            "concluso regolarmente, e dopo di quella non ne risulta partita nessun'altra: "
            "il job non e' stato avviato (cron non eseguito, macchina spenta, unita' "
            "systemd disabilitata)."
        )

    eta = format_seconds(int((now - last_start_at).total_seconds()))
    return (
        f"[notifyhub] l'esecuzione partita il {_stamp(last_start_at)} ({eta} fa) non ha "
        "mai inviato la conclusione: il job E' partito e si e' interrotto a meta' "
        "(macchina caduta, OOM, riavvio, processo ucciso), non e' un cron che non e' "
        "scattato."
    )


def missing_content(
    *,
    receiver_name: str,
    group_name: str,
    schedule: ExpectedSchedule,
    last_notification_at: datetime | None,
    last_start_at: datetime | None,
    expected_since: datetime | None,
    deadline: datetime,
    now: datetime,
) -> str:
    if last_notification_at is not None:
        eta = format_seconds(int((now - last_notification_at).total_seconds()))
        ultimo = f"{_stamp(last_notification_at)} ({eta} fa)"
    else:
        da = expected_since or deadline
        ultimo = f"mai (sorveglianza attiva dal {_stamp(da)})"

    return (
        f'[notifyhub] nessun invio da "{receiver_name}" (gruppo {group_name}): '
        f"atteso {describe_expectation(schedule)}.\n"
        f"[notifyhub] ultima conclusione: {ultimo}\n"
        f"[notifyhub] scadenza superata: {_stamp(deadline)}, controllo del {_stamp(now)}\n"
        + diagnose_phase(
            last_start_at=last_start_at,
            last_notification_at=last_notification_at,
            now=now,
        )
        + "\n[notifyhub] questa notifica l'ha generata NotifyHub, non lo script: nessuna "
        "esecuzione ha inviato niente entro la finestra attesa.\n"
        "[notifyhub] da guardare, in ordine: la macchina e' accesa? il cron e' "
        "ancora in crontab? la rete verso NotifyHub risponde? il job usa "
        "--only-on-failure (in quel caso il successo non manda niente e la "
        "sorveglianza non va usata cosi')?"
    )


def recovered_content(
    *,
    receiver_name: str,
    group_name: str,
    schedule: ExpectedSchedule,
    missing_alerted_at: datetime,
    last_notification_at: datetime,
) -> str:
    silence = int((last_notification_at - missing_alerted_at).total_seconds())
    return (
        f'[notifyhub] "{receiver_name}" (gruppo {group_name}) ha ripreso a inviare '
        f"dopo {format_seconds(max(silence, 0))} dall'allarme di assenza.\n"
        f"[notifyhub] allarme del {_stamp(missing_alerted_at)}, primo invio nuovo il "
        f"{_stamp(last_notification_at)}\n"
        f"[notifyhub] attesa dichiarata: {describe_expectation(schedule)}\n"
        "[notifyhub] sorveglianza riarmata: la prossima assenza torna a segnalare."
    )
