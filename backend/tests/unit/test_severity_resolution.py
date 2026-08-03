"""Unit della catena di risoluzione: precedenze, cache dei pattern compilati,
scansione del contenuto senza troncature."""

import uuid
from dataclasses import dataclass

import pytest

from app.db.types import Severity, SeveritySource
from app.services.severity import (
    InvalidPatternError,
    compile_pattern,
    compiled_pattern_cache_info,
    parse_exit_code,
    resolve_severity,
)


@dataclass
class FakeRule:
    """Sostituisce SeverityRule: resolve_severity legge solo questi attributi e
    non tocca il database."""

    priority: int
    pattern: str
    severity: Severity
    case_insensitive: bool = True
    enabled: bool = True
    id: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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


@pytest.mark.unit
def test_priorita_piu_bassa_vince():
    rules = [
        FakeRule(
            priority=20,
            pattern="attenzione",
            severity=Severity.WARNING,
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
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
