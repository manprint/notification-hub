"""Risoluzione della severity (spec 7) e validazione delle regole RE2 (spec 4.2, D8).

Questo e l'UNICO modulo dell'applicazione autorizzato a importare `re2`: le regex
scritte dagli utenti non devono mai finire nel modulo `re` della standard library,
che non ha timeout e puo degenerare con backtracking catastrofico (invariante I-3).
Un test di lint (tests/unit/test_severity_lint.py) verifica meccanicamente che
`import re` non compaia in nessun modulo che valuta pattern utente.

Le regole esaminano il contenuto INTERO, non un campione: un errore in fondo a un
log da 20 MB deve poter far scattare una regola come uno in prima riga. RE2 e a
tempo lineare nella dimensione dell'input, quindi la scansione completa ha un
costo prevedibile; le due protezioni sono la cache dei pattern compilati (sotto)
e l'offload su thread per i corpi grandi (`resolve_severity_async`).
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import re2

from app.db.types import Severity, SeveritySource

# Sopra questa dimensione la catena gira in un thread separato: scansionare
# qualche megabyte con dieci regole e lavoro CPU sincrono, e sull'event loop
# dell'API bloccherebbe ogni altra richiesta in corso per tutta la durata.
SCAN_THREAD_THRESHOLD_CHARS = 256 * 1024

# Numero di pattern compilati tenuti in memoria. Una compilazione RE2 costa
# molto piu di una ricerca: senza cache ogni regola veniva ricompilata a ogni
# singola ingestione.
COMPILED_PATTERN_CACHE_SIZE = 512


class InvalidPatternError(ValueError):
    """Sollevato quando un pattern non e compilabile da RE2 (spec: 422 in creazione)."""


@lru_cache(maxsize=COMPILED_PATTERN_CACHE_SIZE)
def _compile_cached(effective_pattern: str) -> Any:
    return re2.compile(effective_pattern)


def compile_pattern(pattern: str, case_insensitive: bool) -> Any:
    """Compila un pattern utente con RE2. Solleva InvalidPatternError se non valido.

    Il flag case-insensitive si traduce nel prefisso inline `(?i)`, come da spec 4.2:
    RE2 non ha un parametro IGNORECASE separato dal testo del pattern per il flag
    globale in tutte le versioni dei binding, quindi si usa la forma portabile.

    Il risultato e in cache per (pattern, case_insensitive): gli oggetti compilati
    RE2 sono immutabili e riusabili fra richieste e fra thread. Un pattern non
    valido solleva e non entra in cache, quindi la validazione resta esatta.
    """
    effective = f"(?i){pattern}" if case_insensitive else pattern
    try:
        return _compile_cached(effective)
    except re2.error as exc:
        raise InvalidPatternError(str(exc)) from exc


def compiled_pattern_cache_info() -> Any:
    """Statistiche della cache dei pattern, per diagnostica e test."""
    return _compile_cached.cache_info()


@dataclass(frozen=True)
class EvaluableRule:
    """Una regola pronta per essere valutata, indipendente da dove e conservata.

    Le regole in gioco arrivano da due tabelle diverse (quelle scritte sul
    receiver e quelle dei preset applicati): la catena di valutazione e una
    sola, quindi il motore ragiona su questa forma unica. Chi costruisce la
    lista (services/rule_chain.py) decide l'ordine e lo esprime in `priority`.
    """

    pattern: str
    severity: Severity
    priority: int = 0
    case_insensitive: bool = True
    enabled: bool = True
    id: str = ""
    # Valorizzati solo per le regole che vengono da un preset: servono a dire
    # nella dashboard dove andare a modificare la regola che ha deciso.
    preset_id: str | None = None
    preset_name: str | None = None


@dataclass
class SeverityResolution:
    severity: Severity
    source: SeveritySource
    matched_rule_id: str | None = None
    matched_pattern: str | None = None
    matched_preset_id: str | None = None
    matched_preset_name: str | None = None


def _parse_explicit_severity(value: str | None) -> Severity | None:
    if not value:
        return None
    try:
        return Severity(value.lower())
    except ValueError:
        return None


def parse_exit_code(value: str | None) -> int | None:
    """Legge l'header X-Exit-Code. Un valore non numerico viene ignorato come una
    severity esplicita non valida: l'ingestion non fallisce mai per colpa di
    un'intestazione scritta male (invariante I-7)."""
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def resolve_severity(
    *,
    header_severity: str | None,
    query_severity: str | None,
    rules: Sequence[EvaluableRule],
    content: str,
    default_severity: Severity,
    exit_code: int | None = None,
    exit_code_severity: Severity | None = None,
) -> SeverityResolution:
    """Applica la catena di precedenza della spec 7, estesa con l'exit code:

        1. severity esplicita  (header X-Severity o ?severity=)
        2. exit code != 0      (header X-Exit-Code + politica del receiver)
        3. regole              (match RE2 sul contenuto intero, per priorita:
                                prima quelle del receiver, poi quelle dei preset)
        4. severity di default del receiver

    Il passo 2 sta sopra le regole perche un comando fallito e un fatto oggettivo,
    indipendente da come lo script ha formattato l'output; sta sotto la severity
    esplicita perche quella e una decisione presa apposta da chi invia.

    `content` e il contenuto completo gia normalizzato, non un campione. Una
    severity esplicita non valida (es. "banana") viene ignorata silenziosamente e
    la catena scende al passo successivo, senza far fallire l'ingestion.
    """
    explicit = _parse_explicit_severity(header_severity) or _parse_explicit_severity(query_severity)
    if explicit is not None:
        return SeverityResolution(severity=explicit, source=SeveritySource.EXPLICIT)

    if exit_code is not None and exit_code != 0 and exit_code_severity is not None:
        return SeverityResolution(severity=exit_code_severity, source=SeveritySource.EXIT_CODE)

    # L'id come secondo criterio rende l'ordine totale anche se due regole
    # condividono la priorita: l'unicita e imposta dal database (migrazione
    # 0008), ma la risoluzione non deve dipendere da quel vincolo per essere
    # deterministica.
    for rule in sorted(rules, key=lambda r: (r.priority, str(r.id))):
        if not rule.enabled:
            continue
        compiled = compile_pattern(rule.pattern, rule.case_insensitive)
        if compiled.search(content):
            return SeverityResolution(
                severity=rule.severity,
                source=(
                    SeveritySource.PRESET_RULE
                    if rule.preset_id is not None
                    else SeveritySource.RULE
                ),
                matched_rule_id=str(rule.id),
                matched_pattern=rule.pattern,
                matched_preset_id=rule.preset_id,
                matched_preset_name=rule.preset_name,
            )

    return SeverityResolution(severity=default_severity, source=SeveritySource.RECEIVER_DEFAULT)


async def resolve_severity_async(
    *,
    header_severity: str | None,
    query_severity: str | None,
    rules: Sequence[EvaluableRule],
    content: str,
    default_severity: Severity,
    exit_code: int | None = None,
    exit_code_severity: Severity | None = None,
) -> SeverityResolution:
    """Come resolve_severity, ma sposta la scansione su un thread quando il
    contenuto e grande: e la versione da usare da dentro l'API async."""

    def _run() -> SeverityResolution:
        return resolve_severity(
            header_severity=header_severity,
            query_severity=query_severity,
            rules=rules,
            content=content,
            default_severity=default_severity,
            exit_code=exit_code,
            exit_code_severity=exit_code_severity,
        )

    if len(content) < SCAN_THREAD_THRESHOLD_CHARS:
        return _run()
    return await asyncio.to_thread(_run)
