"""Calcolo dell'attesa: quando un'assenza diventa un allarme.

E' la parte che si puo' sbagliare in silenzio: un conto sbagliato non da errore,
manda un allarme di notte a chi non ha nessun guasto (o, peggio, non lo manda a
chi ce l'ha).
"""

from datetime import UTC, datetime

import pytest

from app.db.types import Severity
from app.models.receiver import Receiver
from app.services.surveillance import (
    DEFAULT_TIMEZONE,
    ExpectedSchedule,
    InvalidScheduleError,
    alert_deadline,
    describe_expectation,
    diagnose_phase,
    format_seconds,
    is_missing,
    missing_content,
    recovered_content,
    reference_instant,
    validate_cron,
    validate_timezone,
)


def _interval(every: int = 86400, grace: int = 1800) -> ExpectedSchedule:
    return ExpectedSchedule(grace_seconds=grace, severity=Severity.CRITICAL, every_seconds=every)


def _cron(expression: str = "0 3 * * *", grace: int = 1800, tz: str | None = None):
    return ExpectedSchedule(
        grace_seconds=grace, severity=Severity.CRITICAL, cron=expression, timezone=tz
    )


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


# --- intervallo fisso -------------------------------------------------------


@pytest.mark.unit
def test_intervallo_scadenza_e_ultimo_invio_piu_finestra():
    ultimo = _at("2026-08-03T03:00:00")
    scadenza = alert_deadline(_interval(), reference=ultimo)
    assert scadenza == _at("2026-08-04T03:30:00")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("adesso", "in_ritardo"),
    [
        ("2026-08-04T03:29:59", False),  # dentro la tolleranza
        ("2026-08-04T03:30:00", False),  # sul limite: non ancora assenza
        ("2026-08-04T03:30:01", True),
        ("2026-08-05T00:00:00", True),
    ],
)
def test_intervallo_confronto_stretto(adesso, in_ritardo):
    ultimo = _at("2026-08-03T03:00:00")
    assert is_missing(_interval(), reference=ultimo, now=_at(adesso)) is in_ritardo


@pytest.mark.unit
def test_intervallo_senza_tolleranza():
    ultimo = _at("2026-08-03T03:00:00")
    schedule = _interval(every=300, grace=0)
    assert alert_deadline(schedule, reference=ultimo) == _at("2026-08-03T03:05:00")


# --- espressione cron -------------------------------------------------------


@pytest.mark.unit
def test_cron_se_ultima_occorrenza_e_arrivata_si_aspetta_la_prossima():
    """L'invio delle 3 di stamattina c'e' stato: la scadenza da mostrare e da
    attendere e' quella di domani, non una scadenza gia' passata."""
    scadenza = alert_deadline(_cron(), reference=_at("2026-08-04T03:00:12"))
    assert scadenza == _at("2026-08-05T03:30:00")


@pytest.mark.unit
def test_cron_se_ultima_occorrenza_non_e_arrivata_la_scadenza_e_quella():
    scadenza = alert_deadline(_cron(), reference=_at("2026-08-03T03:00:12"))
    assert scadenza == _at("2026-08-04T03:30:00")
    assert is_missing(_cron(), reference=_at("2026-08-03T03:00:12"), now=_at("2026-08-04T09:00:00"))


@pytest.mark.unit
def test_cron_nel_weekend_non_allarma_un_job_infrasettimanale():
    """Il motivo per cui l'espressione cron esiste: `0 3 * * 1-5` con un
    intervallo fisso di 24 ore darebbe un falso allarme ogni sabato."""
    schedule = _cron("0 3 * * 1-5")
    ultimo_venerdi = _at("2026-08-07T03:00:10")  # venerdi 7 agosto 2026
    sabato = _at("2026-08-08T12:00:00")
    domenica = _at("2026-08-09T23:00:00")
    assert not is_missing(schedule, reference=ultimo_venerdi, now=sabato)
    assert not is_missing(schedule, reference=ultimo_venerdi, now=domenica)
    # Lunedi alle 3:30 passate, invece, l'assenza e' vera.
    assert is_missing(schedule, reference=ultimo_venerdi, now=_at("2026-08-10T03:31:00"))


@pytest.mark.unit
def test_cron_nel_fuso_dichiarato_non_in_utc():
    """`0 3 * * *` con Europe/Rome vuol dire le 3 di Roma: in agosto sono le
    01:00 UTC, e la tolleranza si conta da quelle."""
    schedule = _cron("0 3 * * *", grace=600, tz="Europe/Rome")
    scadenza = alert_deadline(schedule, reference=_at("2026-08-03T01:00:05"))
    assert scadenza == _at("2026-08-04T01:10:00")


@pytest.mark.unit
def test_cron_attraverso_il_cambio_di_ora_legale():
    """Ultima domenica di ottobre 2026: l'ora legale finisce, le 3 di Roma
    passano da 01:00 a 02:00 UTC. L'orario da rispettare e' quello del muro.

    Il riferimento e' l'esecuzione delle 3 del 25 ottobre, che quel giorno cade
    alle 02:00 UTC (ora solare): la scadenza successiva e' quella del 26, di
    nuovo alle 3 del muro."""
    schedule = _cron("0 3 * * *", grace=0, tz="Europe/Rome")
    scadenza = alert_deadline(schedule, reference=_at("2026-10-25T02:00:05"))
    assert scadenza == _at("2026-10-26T02:00:00")


@pytest.mark.unit
def test_cron_ogni_cinque_minuti():
    schedule = _cron("*/5 * * * *", grace=60)
    ultimo = _at("2026-08-04T10:00:03")
    assert not is_missing(schedule, reference=ultimo, now=_at("2026-08-04T10:05:30"))
    assert is_missing(schedule, reference=ultimo, now=_at("2026-08-04T10:06:30"))


@pytest.mark.unit
def test_cron_con_tolleranza_piu_lunga_del_periodo_allarma_comunque():
    """Regressione: la scadenza si conta dall'ultimo invio, non da adesso.

    Con `*/5 * * * *` e 15 minuti di tolleranza, ancorare il conto ad "adesso"
    faceva scorrere in avanti l'ultima occorrenza a ogni giro del job insieme
    alla scadenza, che restava sempre nel futuro: un receiver muto da ore non
    allarmava mai.
    """
    schedule = _cron("*/5 * * * *", grace=900)
    ultimo = _at("2026-08-04T10:00:03")

    # Prima occorrenza attesa dopo l'invio: 10:05, piu' 15 minuti di tolleranza.
    assert alert_deadline(schedule, reference=ultimo) == _at("2026-08-04T10:20:00")
    assert not is_missing(schedule, reference=ultimo, now=_at("2026-08-04T10:20:00"))
    assert is_missing(schedule, reference=ultimo, now=_at("2026-08-04T10:20:01"))
    # E resta un allarme anche molto piu' tardi, invece di tornare "in orario".
    assert is_missing(schedule, reference=ultimo, now=_at("2026-08-04T18:00:00"))


@pytest.mark.unit
def test_cron_la_scadenza_e_quella_della_prima_esecuzione_mancata():
    """Dopo tre giorni di silenzio la data da mostrare e' la prima scadenza
    saltata, non quella di stanotte: e' l'istante in cui il guasto e' iniziato."""
    schedule = _cron("0 3 * * *", grace=1800)
    scadenza = alert_deadline(schedule, reference=_at("2026-08-01T03:00:07"))
    assert scadenza == _at("2026-08-02T03:30:00")
    assert is_missing(
        schedule, reference=_at("2026-08-01T03:00:07"), now=_at("2026-08-04T09:00:00")
    )


@pytest.mark.unit
def test_cron_riferimento_esattamente_su_una_occorrenza():
    """Un invio arrivato al secondo esatto dell'occorrenza non azzera la
    finestra: si aspetta la successiva, non di nuovo la stessa."""
    schedule = _cron("0 3 * * *", grace=0)
    assert alert_deadline(schedule, reference=_at("2026-08-04T03:00:00")) == _at(
        "2026-08-05T03:00:00"
    )


@pytest.mark.unit
def test_cron_nel_giorno_in_cui_le_due_di_notte_non_esistono():
    """Ultima domenica di marzo: a Roma le 02:00 non esistono, l'orologio salta
    da 02:00 a 03:00. L'attesa resta calcolabile e si sposta sull'ora reale
    (03:00 locali = 01:00 UTC), invece di far fallire il job."""
    schedule = _cron("0 2 * * *", grace=0, tz="Europe/Rome")
    scadenza = alert_deadline(schedule, reference=_at("2026-03-28T01:00:05"))
    assert scadenza == _at("2026-03-29T01:00:00")


@pytest.mark.unit
def test_cron_giorno_del_mese_e_giorno_della_settimana_sono_in_or():
    """Come in crontab: `0 3 1 * 1` scatta il primo del mese OPPURE di lunedi,
    non solo quando le due condizioni valgono insieme."""
    schedule = _cron("0 3 1 * 1", grace=0)
    # Martedi 15 settembre 2026: la prossima e' lunedi 21, non il 1 ottobre.
    assert alert_deadline(schedule, reference=_at("2026-09-15T12:00:00")) == _at(
        "2026-09-21T03:00:00"
    )


# --- da quando si conta -----------------------------------------------------


def _receiver(last_notification_at=None, expected_since=None) -> Receiver:
    receiver = Receiver()
    receiver.last_notification_at = last_notification_at
    receiver.expected_since = expected_since
    return receiver


@pytest.mark.unit
def test_reference_instant_senza_dati_non_decide():
    assert reference_instant(_receiver()) is None


@pytest.mark.unit
def test_reference_instant_prende_il_piu_recente():
    """Sorveglianza accesa oggi su un receiver muto da un mese: si conta da
    quando la sorveglianza guarda, altrimenti l'allarme parte al primo giro del
    job per un silenzio che nessuno aveva chiesto di riempire."""
    vecchio = _at("2026-07-01T10:00:00")
    acceso = _at("2026-08-01T10:00:00")
    assert reference_instant(_receiver(vecchio, acceso)) == acceso
    # E viceversa: dopo un invio vero comanda l'invio.
    assert reference_instant(_receiver(_at("2026-08-02T10:00:00"), acceso)) == _at(
        "2026-08-02T10:00:00"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ultimo", "da"),
    [
        (_at("2026-08-02T10:00:00"), None),
        (None, _at("2026-08-02T10:00:00")),
    ],
)
def test_reference_instant_con_un_solo_valore(ultimo, da):
    assert reference_instant(_receiver(ultimo, da)) == _at("2026-08-02T10:00:00")


# --- validazione ------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "espressione",
    [
        "0 3 * * *",
        "*/5 * * * *",
        "0 3 * * 1-5",
        "15,45 * * * *",
        "0 0 1 * *",
        # Il 29 febbraio esiste, anche se solo negli anni bisestili: rara, non
        # impossibile, e va accettata.
        "0 0 29 2 *",
    ],
)
def test_validate_cron_accetta(espressione):
    assert validate_cron(f"  {espressione}  ") == espressione


@pytest.mark.unit
@pytest.mark.parametrize(
    "espressione",
    [
        "",
        "   ",
        "0 3 * *",  # 4 campi
        "0 3 * * * *",  # 6 campi: croniter li accetta, qui no
        "@daily",  # comodo ma non e' cio' che sta in crontab
        "99 3 * * *",
        "non un cron",
        "0 3 * * * ; rm -rf /",
        "0 " + "3" * 200 + " * * *",
        # Sintatticamente valide per croniter ma senza alcuna occorrenza: il 30
        # febbraio e il 31 aprile non arrivano mai. Salvarle vorrebbe dire una
        # sorveglianza che non sorveglia, muta anche quando il job muore.
        "0 0 30 2 *",
        "0 0 31 4 *",
    ],
)
def test_validate_cron_rifiuta(espressione):
    with pytest.raises(InvalidScheduleError):
        validate_cron(espressione)


@pytest.mark.unit
@pytest.mark.parametrize("nome", ["UTC", "Europe/Rome", "America/New_York"])
def test_validate_timezone_accetta(nome):
    assert validate_timezone(nome) == nome


@pytest.mark.unit
@pytest.mark.parametrize("nome", ["", "  ", "Europa/Roma", "Mars/Olympus", "../../etc/passwd"])
def test_validate_timezone_rifiuta(nome):
    with pytest.raises(InvalidScheduleError):
        validate_timezone(nome)


# --- testi ------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("secondi", "atteso"),
    [
        (0, "0s"),
        (45, "45s"),
        (90, "1m30s"),
        (3600, "1h00m"),
        (5430, "1h30m"),
        (86400, "1g"),
        (97200, "1g03h"),
        (604800, "7g"),
    ],
)
def test_format_seconds(secondi, atteso):
    assert format_seconds(secondi) == atteso


@pytest.mark.unit
def test_describe_expectation():
    assert describe_expectation(_interval()) == "ogni 1g, tolleranza 30m00s"
    assert describe_expectation(_cron(tz="Europe/Rome")) == (
        "cron `0 3 * * *` (Europe/Rome), tolleranza 30m00s"
    )
    # Senza fuso dichiarato si dice quale si sta usando, non si tace.
    assert DEFAULT_TIMEZONE in describe_expectation(_cron())


@pytest.mark.unit
def test_missing_content_dice_cosa_guardare():
    testo = missing_content(
        receiver_name="elog-test",
        group_name="Maritime",
        schedule=_interval(),
        last_notification_at=_at("2026-08-03T03:00:00"),
        last_start_at=None,
        expected_since=_at("2026-07-01T00:00:00"),
        deadline=_at("2026-08-04T03:30:00"),
        now=_at("2026-08-04T04:00:00"),
    )
    prima_riga = testo.split("\n")[0]
    # La prima riga e' l'unica che si vede nell'elenco: deve bastare da sola.
    assert "nessun invio" in prima_riga
    assert "elog-test" in prima_riga and "Maritime" in prima_riga
    assert "2026-08-03T03:00:00Z" in testo
    assert "1g01h fa" in testo
    assert "2026-08-04T03:30:00Z" in testo
    assert "--only-on-failure" in testo


@pytest.mark.unit
def test_missing_content_quando_non_e_mai_arrivato_niente():
    testo = missing_content(
        receiver_name="nuovo",
        group_name="G",
        schedule=_cron(),
        last_notification_at=None,
        last_start_at=None,
        expected_since=_at("2026-08-01T00:00:00"),
        deadline=_at("2026-08-02T03:30:00"),
        now=_at("2026-08-02T04:00:00"),
    )
    assert "mai (sorveglianza attiva dal 2026-08-01T00:00:00Z)" in testo


@pytest.mark.unit
def test_recovered_content_dice_quanto_e_durato_il_silenzio():
    testo = recovered_content(
        receiver_name="elog-test",
        group_name="Maritime",
        schedule=_interval(),
        missing_alerted_at=_at("2026-08-04T03:31:00"),
        last_notification_at=_at("2026-08-05T10:33:00"),
    )
    assert "ha ripreso a inviare" in testo.split("\n")[0]
    assert "1g07h" in testo
    assert "riarmata" in testo


# --- fase dell'esecuzione ---------------------------------------------------


@pytest.mark.unit
def test_diagnose_phase_senza_ping_di_avvio_dichiara_di_non_sapere():
    """Non avendo il dato, il testo non deve inventare una diagnosi: dice che
    manca e come ottenerlo."""
    testo = diagnose_phase(
        last_start_at=None,
        last_notification_at=_at("2026-08-03T03:00:00"),
        now=_at("2026-08-04T04:00:00"),
    )
    assert "non e' possibile dire" in testo
    assert "--ping-start" in testo


@pytest.mark.unit
def test_diagnose_phase_partito_e_mai_concluso():
    """Il caso che i ping di avvio servono a distinguere: la macchina e' caduta a
    meta' esecuzione."""
    testo = diagnose_phase(
        last_start_at=_at("2026-08-04T03:00:05"),
        last_notification_at=_at("2026-08-03T03:12:00"),
        now=_at("2026-08-04T05:00:05"),
    )
    assert "E' partito e si e' interrotto" in testo
    assert "2026-08-04T03:00:05Z" in testo
    assert "2h00m fa" in testo


@pytest.mark.unit
def test_diagnose_phase_mai_avviato():
    """Ultimo avvio concluso regolarmente e nessun avvio dopo: il cron non e'
    scattato."""
    testo = diagnose_phase(
        last_start_at=_at("2026-08-03T03:00:05"),
        last_notification_at=_at("2026-08-03T03:12:00"),
        now=_at("2026-08-04T05:00:00"),
    )
    assert "non e' stato avviato" in testo


@pytest.mark.unit
def test_diagnose_phase_avviato_senza_nessuna_conclusione_mai():
    testo = diagnose_phase(
        last_start_at=_at("2026-08-04T03:00:05"),
        last_notification_at=None,
        now=_at("2026-08-04T06:00:05"),
    )
    assert "E' partito e si e' interrotto" in testo


@pytest.mark.unit
def test_missing_content_include_la_diagnosi_della_fase():
    testo = missing_content(
        receiver_name="elog-test",
        group_name="Maritime",
        schedule=_interval(),
        last_notification_at=_at("2026-08-03T03:00:00"),
        last_start_at=_at("2026-08-04T03:00:05"),
        expected_since=None,
        deadline=_at("2026-08-04T03:30:00"),
        now=_at("2026-08-04T04:00:05"),
    )
    assert "E' partito e si e' interrotto" in testo
    # La conclusione resta quella vera: un avvio non e' una conclusione.
    assert "ultima conclusione: 2026-08-03T03:00:00Z" in testo
