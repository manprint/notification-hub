import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import ReceiverStatus, Severity


class ReceiverCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_body_bytes: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int = Field(default=60, ge=0)
    default_severity: Severity = Severity.INFO
    # Severity applicata quando arriva X-Exit-Code diverso da zero.
    # None esplicito = l'exit code non influenza la severity.
    exit_code_severity: Severity | None = Severity.CRITICAL


class ReceiverUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: ReceiverStatus | None = None
    max_body_bytes: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int | None = Field(default=None, ge=0)
    default_severity: Severity | None = None
    # Qui None e un valore legittimo (disattiva la politica sull'exit code), non
    # "campo assente": l'endpoint distingue i due casi con model_fields_set.
    exit_code_severity: Severity | None = None


class ReceiverOut(BaseModel):
    # Vedi nota in schemas/group.py: model_validate su un oggetto ORM richiede
    # uuid.UUID sui campi id, non str.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    slug: str
    name: str
    status: ReceiverStatus
    ingestion_module: str
    default_severity: Severity
    exit_code_severity: Severity | None = None
    max_body_bytes: int
    rate_limit_per_min: int
    rejected_last_24h: int = 0


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


class TestSeverityOut(BaseModel):
    severity: Severity
    source: str
    matched_rule_id: str | None = None
    matched_pattern: str | None = None
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
