"""Risoluzione della severity (spec 7) e validazione delle regole RE2 (spec 4.2, D8).

Questo e l'UNICO modulo dell'applicazione autorizzato a importare `re2`: le regex
scritte dagli utenti non devono mai finire nel modulo `re` della standard library,
che non ha timeout e puo degenerare con backtracking catastrofico (invariante I-3).
Un test di lint (tests/unit/test_severity_lint.py) verifica meccanicamente che
`import re` non compaia in nessun modulo che valuta pattern utente.
"""

from dataclasses import dataclass
from typing import Any

import re2

from app.db.types import Severity, SeveritySource
from app.models.severity_rule import SeverityRule

SEVERITY_RULE_MAX_CONTENT_BYTES = 8192


class InvalidPatternError(ValueError):
    """Sollevato quando un pattern non e compilabile da RE2 (spec: 422 in creazione)."""


def compile_pattern(pattern: str, case_insensitive: bool) -> Any:
    """Compila un pattern utente con RE2. Solleva InvalidPatternError se non valido.

    Il flag case-insensitive si traduce nel prefisso inline `(?i)`, come da spec 4.2:
    RE2 non ha un parametro IGNORECASE separato dal testo del pattern per il flag
    globale in tutte le versioni dei binding, quindi si usa la forma portabile.
    """
    effective = f"(?i){pattern}" if case_insensitive else pattern
    try:
        return re2.compile(effective)
    except re2.error as exc:
        raise InvalidPatternError(str(exc)) from exc


@dataclass
class SeverityResolution:
    severity: Severity
    source: SeveritySource
    matched_rule_id: str | None = None
    matched_pattern: str | None = None


def _parse_explicit_severity(value: str | None) -> Severity | None:
    if not value:
        return None
    try:
        return Severity(value.lower())
    except ValueError:
        return None


def resolve_severity(
    *,
    header_severity: str | None,
    query_severity: str | None,
    rules: list[SeverityRule],
    content_sample: str,
    default_severity: Severity,
) -> SeverityResolution:
    """Applica la catena di precedenza della spec 7: esplicita -> regole -> default.

    `content_sample` deve gia essere limitato agli 8KB richiesti dalla spec: la
    verita sul limite vive nel chiamante (services/ingest.py), che ha il buffer.
    Una severity esplicita non valida (es. "banana") viene ignorata silenziosamente
    e la catena scende al passo successivo, senza far fallire l'ingestion.
    """
    explicit = _parse_explicit_severity(header_severity) or _parse_explicit_severity(query_severity)
    if explicit is not None:
        return SeverityResolution(severity=explicit, source=SeveritySource.EXPLICIT)

    sample = content_sample[:SEVERITY_RULE_MAX_CONTENT_BYTES]
    for rule in sorted(rules, key=lambda r: r.priority):
        if not rule.enabled:
            continue
        compiled = compile_pattern(rule.pattern, rule.case_insensitive)
        if compiled.search(sample):
            return SeverityResolution(
                severity=rule.severity,
                source=SeveritySource.RULE,
                matched_rule_id=str(rule.id),
                matched_pattern=rule.pattern,
            )

    return SeverityResolution(severity=default_severity, source=SeveritySource.RECEIVER_DEFAULT)
