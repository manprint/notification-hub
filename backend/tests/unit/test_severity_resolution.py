"""Unit della catena di risoluzione: precedenze, cache dei pattern compilati,
scansione del contenuto senza troncature."""

import uuid

import pytest

from app.db.types import Severity, SeveritySource
from app.services.severity import (
    EvaluableRule,
    InvalidPatternError,
    compile_pattern,
    compiled_pattern_cache_info,
    duration_exceeds_threshold,
    parse_duration_ms,
    parse_exit_code,
    resolve_severity,
)


def FakeRule(**kwargs) -> EvaluableRule:  # noqa: N802
    """Regola di prova: EvaluableRule con un id di default, cosi i test parlano
    solo dei campi che stanno verificando."""
    kwargs.setdefault("id", "00000000-0000-0000-0000-000000000001")
    return EvaluableRule(**kwargs)


def _resolve(**overrides):
    kwargs = {
        "header_severity": None,
        "query_severity": None,
        "rules": [],
        "content": "",
        "default_severity": Severity.INFO,
    }
    kwargs.update(overrides)
    return resolve_severity(**kwargs)


@pytest.mark.unit
def test_severity_esplicita_vince_su_tutto():
    rules = [FakeRule(priority=10, pattern="ERRORE", severity=Severity.ERROR)]
    res = _resolve(
        header_severity="debug",
        rules=rules,
        content="ERRORE grave",
        exit_code=5,
        exit_code_severity=Severity.CRITICAL,
    )
    assert (res.severity, res.source) == (Severity.DEBUG, SeveritySource.EXPLICIT)


@pytest.mark.unit
def test_header_vince_sulla_query():
    res = _resolve(header_severity="warning", query_severity="debug")
    assert res.severity == Severity.WARNING


@pytest.mark.unit
def test_severity_esplicita_non_valida_ignorata():
    res = _resolve(header_severity="banana", default_severity=Severity.INFO)
    assert (res.severity, res.source) == (Severity.INFO, SeveritySource.RECEIVER_DEFAULT)


@pytest.mark.unit
def test_exit_code_vince_sulle_regole():
    rules = [FakeRule(priority=10, pattern="tutto bene", severity=Severity.DEBUG)]
    res = _resolve(
        rules=rules,
        content="tutto bene",
        exit_code=2,
        exit_code_severity=Severity.CRITICAL,
    )
    assert (res.severity, res.source) == (Severity.CRITICAL, SeveritySource.EXIT_CODE)


@pytest.mark.unit
def test_exit_code_zero_non_interviene():
    rules = [FakeRule(priority=10, pattern="tutto bene", severity=Severity.DEBUG)]
    res = _resolve(
        rules=rules, content="tutto bene", exit_code=0, exit_code_severity=Severity.CRITICAL
    )
    assert (res.severity, res.source) == (Severity.DEBUG, SeveritySource.RULE)


@pytest.mark.unit
def test_exit_code_senza_politica_non_interviene():
    res = _resolve(content="qualsiasi", exit_code=7, exit_code_severity=None)
    assert res.source == SeveritySource.RECEIVER_DEFAULT


# --- durata oltre la soglia ------------------------------------------------


def _slow(**overrides):
    """Risoluzione con una politica di durata attiva: soglia 10 minuti -> error."""
    kwargs = {
        "duration_threshold_seconds": 600,
        "duration_severity": Severity.ERROR,
    }
    kwargs.update(overrides)
    return _resolve(**kwargs)


@pytest.mark.unit
def test_durata_oltre_soglia_vince_sulle_regole():
    rules = [FakeRule(priority=10, pattern="tutto bene", severity=Severity.DEBUG)]
    res = _slow(rules=rules, content="tutto bene", duration_ms=1_200_000)
    assert (res.severity, res.source) == (Severity.ERROR, SeveritySource.DURATION)
    assert res.duration_exceeded is True


@pytest.mark.unit
def test_durata_sotto_soglia_lascia_decidere_le_regole():
    rules = [FakeRule(priority=10, pattern="tutto bene", severity=Severity.DEBUG)]
    res = _slow(rules=rules, content="tutto bene", duration_ms=300_000)
    assert (res.severity, res.source) == (Severity.DEBUG, SeveritySource.RULE)
    assert res.duration_exceeded is False


@pytest.mark.unit
def test_durata_esatta_sulla_soglia_non_scatta():
    """La soglia e "avvisami se supera", non "durata massima ammessa"."""
    res = _slow(content="", duration_ms=600_000)
    assert res.source == SeveritySource.RECEIVER_DEFAULT


@pytest.mark.unit
def test_durata_senza_politica_non_interviene():
    res = _resolve(content="", duration_ms=99_999_999)
    assert res.source == SeveritySource.RECEIVER_DEFAULT
    assert res.duration_exceeded is False


@pytest.mark.unit
def test_soglia_senza_durata_dichiarata_non_interviene():
    """Un mittente che non usa il wrapper non manda l'header: la soglia tace."""
    res = _slow(content="", duration_ms=None)
    assert res.source == SeveritySource.RECEIVER_DEFAULT


@pytest.mark.unit
def test_fra_exit_code_e_durata_vince_la_piu_grave():
    lenta = _slow(
        content="",
        duration_ms=1_200_000,
        exit_code=1,
        exit_code_severity=Severity.WARNING,
    )
    assert (lenta.severity, lenta.source) == (Severity.ERROR, SeveritySource.DURATION)

    fallita = _slow(
        content="",
        duration_ms=1_200_000,
        exit_code=1,
        exit_code_severity=Severity.CRITICAL,
    )
    assert (fallita.severity, fallita.source) == (Severity.CRITICAL, SeveritySource.EXIT_CODE)
    # Anche quando ha deciso l'exit code, la lentezza resta dichiarata.
    assert fallita.duration_exceeded is True


@pytest.mark.unit
def test_pari_severity_fra_exit_code_e_durata_dichiara_exit_code():
    res = _slow(
        content="",
        duration_ms=1_200_000,
        exit_code=2,
        exit_code_severity=Severity.ERROR,
    )
    assert (res.severity, res.source) == (Severity.ERROR, SeveritySource.EXIT_CODE)


@pytest.mark.unit
def test_severity_esplicita_batte_la_durata_ma_la_lentezza_resta_visibile():
    res = _slow(header_severity="info", content="", duration_ms=1_200_000)
    assert (res.severity, res.source) == (Severity.INFO, SeveritySource.EXPLICIT)
    assert res.duration_exceeded is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("duration_ms", "soglia", "severity", "atteso"),
    [
        (600_001, 600, Severity.ERROR, True),
        (600_000, 600, Severity.ERROR, False),
        (600_001, None, Severity.ERROR, False),
        (600_001, 600, None, False),
        (None, 600, Severity.ERROR, False),
    ],
)
def test_duration_exceeds_threshold(duration_ms, soglia, severity, atteso):
    assert duration_exceeds_threshold(duration_ms, soglia, severity) is atteso


@pytest.mark.unit
@pytest.mark.parametrize(
    ("grezzo", "atteso"),
    [
        ("0", 0),
        ("750123", 750123),
        (" 42 ", 42),
        ("-1", None),  # una durata negativa non e una durata
        ("1.5", None),  # millisecondi interi, niente decimali
        ("boh", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_duration_ms(grezzo, atteso):
    assert parse_duration_ms(grezzo) == atteso


@pytest.mark.unit
def test_priorita_piu_bassa_vince():
    rules = [
        FakeRule(
            priority=20,
            pattern="attenzione",
            severity=Severity.WARNING,
            id="00000000-0000-0000-0000-000000000002",
        ),
        FakeRule(priority=10, pattern="ERRORE", severity=Severity.ERROR),
    ]
    res = _resolve(rules=rules, content="ERRORE con attenzione")
    assert (res.severity, res.matched_pattern) == (Severity.ERROR, "ERRORE")


@pytest.mark.unit
def test_regola_disattivata_saltata():
    rules = [FakeRule(priority=10, pattern="ERRORE", severity=Severity.ERROR, enabled=False)]
    res = _resolve(rules=rules, content="ERRORE", default_severity=Severity.INFO)
    assert res.source == SeveritySource.RECEIVER_DEFAULT


@pytest.mark.unit
def test_case_insensitive_disattivabile():
    rules = [
        FakeRule(priority=10, pattern="ERRORE", severity=Severity.ERROR, case_insensitive=False)
    ]
    assert _resolve(rules=rules, content="errore").source == SeveritySource.RECEIVER_DEFAULT
    assert _resolve(rules=rules, content="ERRORE").source == SeveritySource.RULE


@pytest.mark.unit
def test_nessuna_troncatura_del_contenuto():
    """Il vecchio motore campionava 8192 caratteri: quanto stava oltre non
    poteva far scattare nessuna regola."""
    rules = [FakeRule(priority=10, pattern="AGO", severity=Severity.CRITICAL)]
    pagliaio = "x" * 200_000 + "AGO"
    res = _resolve(rules=rules, content=pagliaio)
    assert (res.severity, res.source) == (Severity.CRITICAL, SeveritySource.RULE)


@pytest.mark.unit
def test_regola_di_preset_dichiara_la_sua_origine():
    """Chi legge la notifica deve sapere se correggere la regola sul receiver o
    il preset condiviso."""
    rules = [
        FakeRule(
            priority=0,
            pattern="ERRORE",
            severity=Severity.ERROR,
            preset_id="11111111-1111-1111-1111-111111111111",
            preset_name="Bash generico",
        )
    ]
    res = _resolve(rules=rules, content="ERRORE grave")
    assert res.source == SeveritySource.PRESET_RULE
    assert res.matched_preset_name == "Bash generico"


@pytest.mark.unit
def test_regola_propria_del_receiver_non_ha_preset():
    rules = [FakeRule(priority=0, pattern="ERRORE", severity=Severity.ERROR)]
    res = _resolve(rules=rules, content="ERRORE grave")
    assert res.source == SeveritySource.RULE
    assert (res.matched_preset_id, res.matched_preset_name) == (None, None)


@pytest.mark.unit
def test_pattern_compilato_una_volta_sola():
    pattern = f"cache-test-{uuid.uuid4().hex}"
    prima = compiled_pattern_cache_info()
    compile_pattern(pattern, True)
    compile_pattern(pattern, True)
    compile_pattern(pattern, True)
    dopo = compiled_pattern_cache_info()
    assert dopo.misses - prima.misses == 1
    assert dopo.hits - prima.hits == 2


@pytest.mark.unit
def test_maiuscole_e_minuscole_sono_pattern_distinti_in_cache():
    pattern = f"case-test-{uuid.uuid4().hex}"
    prima = compiled_pattern_cache_info()
    compile_pattern(pattern, True)
    compile_pattern(pattern, False)
    dopo = compiled_pattern_cache_info()
    assert dopo.misses - prima.misses == 2


@pytest.mark.unit
def test_pattern_non_valido_non_entra_in_cache():
    with pytest.raises(InvalidPatternError):
        compile_pattern("(non chiuso", True)
    with pytest.raises(InvalidPatternError):
        compile_pattern("(non chiuso", True)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("grezzo", "atteso"),
    [("0", 0), ("3", 3), (" 12 ", 12), ("-1", -1), ("boh", None), ("", None), (None, None)],
)
def test_parse_exit_code(grezzo, atteso):
    assert parse_exit_code(grezzo) == atteso
