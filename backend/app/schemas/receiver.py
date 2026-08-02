import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import ReceiverStatus, Severity


class ReceiverCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_body_bytes: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int = Field(default=60, ge=0)
    default_severity: Severity = Severity.INFO


class ReceiverUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: ReceiverStatus | None = None
    max_body_bytes: int | None = Field(default=None, ge=1)
    rate_limit_per_min: int | None = Field(default=None, ge=0)
    default_severity: Severity | None = None


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
    max_body_bytes: int
    rate_limit_per_min: int
    rejected_last_24h: int = 0


class SeverityRuleCreate(BaseModel):
    priority: int = Field(ge=0)
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


class TestSeverityIn(BaseModel):
    content: str = Field(min_length=1)
    header_severity: str | None = None


class TestSeverityOut(BaseModel):
    severity: Severity
    source: str
    matched_rule_id: str | None = None
    matched_pattern: str | None = None


class DeleteImpactOut(BaseModel):
    receivers: int
    notifications: int
    deliveries: int
