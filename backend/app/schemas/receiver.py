import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.types import ReceiverStatus, Severity

DURATION_POLICY_HALF_CONFIGURED = (
    "duration_threshold_seconds and duration_severity must be set together: "
    "a threshold without a severity has nothing to assign, a severity without a "
    "threshold never fires. Send both as null to disable the duration policy."
)

EXPECTED_POLICY_HALF_CONFIGURED = (
    "The expected-schedule policy needs exactly one of expected_every_seconds or "
    "expected_cron, plus expected_grace_seconds and missing_severity. Send all of "
    "them as null to disable the surveillance."
)
EXPECTED_POLICY_BOTH_MODES = (
    "expected_every_seconds and expected_cron are two ways to say the same thing: "
    "set one or the other, not both."
)
EXPECTED_TIMEZONE_WITHOUT_CRON = (
    "expected_timezone only means something together with expected_cron: an "
    "interval has no wall-clock time to place in a zone."
)


def _validate_expected_fields(
    *,
    every_seconds: int | None,
    cron: str | None,
    timezone: str | None,
    grace_seconds: int | None,
    severity: Severity | None,
) -> None:
    """Coerenza della politica di attesa sullo stato FINALE, usata sia dai
    validator degli schemi sia dall'endpoint di PATCH.

    Il messaggio deve dire quale pezzo manca: e' una configurazione che si sbaglia
    facilmente (quattro campi), e un 422 generico costringerebbe a indovinare."""
    from app.services.surveillance import InvalidScheduleError, validate_cron, validate_timezone

    active = any(
        value is not None for value in (every_seconds, cron, grace_seconds, severity, timezone)
    )
    if not active:
        return

    if every_seconds is not None and cron is not None:
        raise ValueError(EXPECTED_POLICY_BOTH_MODES)
    if (every_seconds is None and cron is None) or grace_seconds is None or severity is None:
        raise ValueError(EXPECTED_POLICY_HALF_CONFIGURED)
    if timezone is not None and cron is None:
        raise ValueError(EXPECTED_TIMEZONE_WITHOUT_CRON)

    try:
        if cron is not None:
            validate_cron(cron)
        if timezone is not None:
            validate_timezone(timezone)
    except InvalidScheduleError as exc:
        raise ValueError(str(exc)) from exc


class ReceiverCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_body_bytes: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int = Field(default=60, ge=0)
    default_severity: Severity = Severity.INFO
    # Severity applicata quando arriva X-Exit-Code diverso da zero.
    # None esplicito = l'exit code non influenza la severity.
    exit_code_severity: Severity | None = Severity.CRITICAL
    # Soglia di durata dell'esecuzione (header X-Duration-Ms) e severity da
    # applicare quando viene superata. Default disattivo: quanto sia "troppo
    # lento" dipende dal singolo job, non esiste un valore ragionevole per tutti.
    duration_threshold_seconds: int | None = Field(default=None, ge=1)
    duration_severity: Severity | None = None
    # Sorveglianza dell'attesa (dead man's switch): ogni quanto ci si aspetta un
    # invio, con quale tolleranza e con quale severity segnalare l'assenza. Uno
    # solo fra intervallo ed espressione cron. Default spenta: quanto spesso
    # debba parlare un job lo sa solo chi l'ha messo in crontab.
    expected_every_seconds: int | None = Field(default=None, ge=1)
    expected_cron: str | None = Field(default=None, max_length=100)
    expected_timezone: str | None = Field(default=None, max_length=64)
    expected_grace_seconds: int | None = Field(default=None, ge=0)
    missing_severity: Severity | None = None

    @model_validator(mode="after")
    def _duration_policy_complete(self) -> Self:
        if (self.duration_threshold_seconds is None) != (self.duration_severity is None):
            raise ValueError(DURATION_POLICY_HALF_CONFIGURED)
        return self

    @model_validator(mode="after")
    def _expected_policy_complete(self) -> Self:
        _validate_expected_fields(
            every_seconds=self.expected_every_seconds,
            cron=self.expected_cron,
            timezone=self.expected_timezone,
            grace_seconds=self.expected_grace_seconds,
            severity=self.missing_severity,
        )
        return self


class ReceiverUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: ReceiverStatus | None = None
    max_body_bytes: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int | None = Field(default=None, ge=0)
    default_severity: Severity | None = None
    # Qui None e un valore legittimo (disattiva la politica sull'exit code), non
    # "campo assente": l'endpoint distingue i due casi con model_fields_set.
    exit_code_severity: Severity | None = None
    # Idem: None disattiva. La coerenza della coppia non si puo verificare qui,
    # perche una PATCH puo cambiare solo una delle due lasciando l'altra al
    # valore gia salvato: il controllo sta nell'endpoint, sullo stato finale.
    duration_threshold_seconds: int | None = Field(default=None, ge=1)
    duration_severity: Severity | None = None
    # Come sopra: None disattiva, e la coerenza si verifica sullo stato finale
    # nell'endpoint, perche una PATCH puo toccare un solo campo dei cinque.
    expected_every_seconds: int | None = Field(default=None, ge=1)
    expected_cron: str | None = Field(default=None, max_length=100)
    expected_timezone: str | None = Field(default=None, max_length=64)
    expected_grace_seconds: int | None = Field(default=None, ge=0)
    missing_severity: Severity | None = None


class ReceiverOut(BaseModel):
    # Vedi nota in schemas/group.py: model_validate su un oggetto ORM richiede
    # uuid.UUID sui campi id, non str.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    slug: str
    # URL completa a cui inviare, decisa dal server e non dal browser: la stessa
    # che finisce nello script scaricabile, cosi' i due non possono divergere
    # (vedi core/urls.py). Valorizzata dagli endpoint, che sono i soli a vedere
    # la richiesta in corso.
    ingest_url: str = ""
    name: str
    status: ReceiverStatus
    ingestion_module: str
    default_severity: Severity
    exit_code_severity: Severity | None = None
    duration_threshold_seconds: int | None = None
    duration_severity: Severity | None = None
    max_body_bytes: int
    rate_limit_per_min: int
    rejected_last_24h: int = 0
    # Sorveglianza dell'attesa: configurazione...
    expected_every_seconds: int | None = None
    expected_cron: str | None = None
    expected_timezone: str | None = None
    expected_grace_seconds: int | None = None
    missing_severity: Severity | None = None
    # ...e stato, che e' la parte che si guarda davvero: quando e arrivato
    # l'ultimo invio vero, se l'assenza e gia stata segnalata e entro quando e
    # atteso il prossimo. La scadenza la calcola il server (endpoint), perche il
    # conto con l'espressione cron e il suo fuso non si fa nel browser.
    last_notification_at: datetime | None = None
    # Ultimo ping di avvio (X-Phase: start), separato dalla conclusione:
    # distingue "non e partito" da "partito e mai finito".
    last_start_at: datetime | None = None
    missing_alerted_at: datetime | None = None
    expected_since: datetime | None = None
    expected_deadline_at: datetime | None = None
    expected_late: bool = False


class SeverityRuleCreate(BaseModel):
    # Priorita opzionale: se assente il backend accoda la regola in fondo
    # (massima priorita esistente + 10), cosi la creazione dalla UI non deve
    # indovinare un numero libero.
    priority: int | None = Field(default=None, ge=0)
    pattern: str = Field(min_length=1, max_length=200)
    case_insensitive: bool = True
    severity: Severity
    enabled: bool = True


class SeverityRuleUpdate(BaseModel):
    priority: int | None = Field(default=None, ge=0)
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    case_insensitive: bool | None = None
    severity: Severity | None = None
    enabled: bool | None = None


class SeverityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    receiver_id: uuid.UUID
    priority: int
    pattern: str
    case_insensitive: bool
    severity: Severity
    enabled: bool


class SeverityRuleReorderIn(BaseModel):
    """Elenco completo delle regole del receiver nell'ordine di valutazione
    voluto: il backend rinumera le priorita 10, 20, 30..."""

    rule_ids: list[uuid.UUID] = Field(min_length=1)


class TestSeverityIn(BaseModel):
    content: str = Field(min_length=1)
    header_severity: str | None = None
    exit_code: int | None = None
    # Durata da simulare, negli stessi millisecondi dell'header X-Duration-Ms:
    # serve a provare la soglia senza dover far girare davvero un job lento.
    duration_ms: int | None = Field(default=None, ge=0)


class TestSeverityOut(BaseModel):
    severity: Severity
    source: str
    matched_rule_id: str | None = None
    matched_pattern: str | None = None
    duration_exceeded: bool = False
    # Valorizzato quando a decidere e stata la regola di un preset: senza,
    # l'utente non saprebbe dove andare a modificarla.
    matched_preset_id: str | None = None
    matched_preset_name: str | None = None


class SeverityReplayItemOut(BaseModel):
    """Una notifica gia arrivata, rivalutata con le regole attuali: serve a
    vedere l'effetto di una modifica prima di applicarla (spec 9.3)."""

    notification_id: uuid.UUID
    received_at: datetime
    content_preview: str
    truncated: bool
    stored_severity: Severity
    stored_source: str
    replayed_severity: Severity
    replayed_source: str
    matched_rule_id: str | None = None
    matched_pattern: str | None = None
    matched_preset_name: str | None = None
    changed: bool


class SeverityReplayOut(BaseModel):
    items: list[SeverityReplayItemOut]
    changed_count: int


class DeleteImpactOut(BaseModel):
    receivers: int
    notifications: int
    deliveries: int
