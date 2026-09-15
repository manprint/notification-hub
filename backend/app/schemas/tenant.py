import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import TenantStatus


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
    max_notifications_per_day: int | None = Field(default=None, ge=1)
    max_storage_bytes: int | None = Field(default=None, ge=1)
    retention_days: int | None = Field(default=None, ge=1)
    audit_retention_days: int | None = Field(default=None, ge=1)
