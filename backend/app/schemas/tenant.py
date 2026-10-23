import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import INT4_MAX, TenantStatus

# Colonna BIGINT (migrazione 0001): un valore piu grande non entra nel bind e
# diventava un 500 invece di un 422.
BIGINT_MAX = 9_223_372_036_854_775_807


class TenantOut(BaseModel):
    # Vedi nota in schemas/group.py sul motivo di uuid.UUID invece di str.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    max_body_bytes: int
    max_notifications_per_day: int | None
    max_storage_bytes: int | None
    retention_days: int | None
    # Ritenzione dell'audit, separata da quella delle notifiche perche' l'audit
    # deve sopravvivere a cio' che descrive (spec 9.6). NULL = illimitata.
    audit_retention_days: int | None
    status: TenantStatus


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    max_body_bytes: int | None = Field(default=None, ge=1, le=20_971_520)
    max_notifications_per_day: int | None = Field(default=None, ge=1, le=INT4_MAX)
    max_storage_bytes: int | None = Field(default=None, ge=1, le=BIGINT_MAX)
    retention_days: int | None = Field(default=None, ge=1, le=INT4_MAX)
    audit_retention_days: int | None = Field(default=None, ge=1, le=INT4_MAX)
