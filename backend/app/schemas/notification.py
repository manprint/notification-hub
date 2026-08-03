import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.types import NotificationStatus, Severity

LIST_PREVIEW_CHARS = 500  # spec 9.5: la lista non restituisce il content completo


class NotificationListItemOut(BaseModel):
    id: str
    receiver_id: str
    content_preview: str
    content_size: int
    content_normalized: bool
    storage_backend: str
    severity: Severity
    severity_source: str
    status: NotificationStatus
    received_at: datetime


class NotificationListOut(BaseModel):
    notifications: list[NotificationListItemOut]
    next_cursor: str | None
    unread_count: int


class NotificationDetailOut(BaseModel):
    id: str
    receiver_id: str
    content: str | None
    content_url: str | None
    content_preview: str
    content_size: int
    content_normalized: bool
    severity: Severity
    severity_source: str
    matched_pattern: str | None
    status: NotificationStatus
    received_at: datetime
    source_ip: str | None


class MarkStatusIn(BaseModel):
    status: NotificationStatus


class BulkReadIn(BaseModel):
    """Segna in blocco per filtro (spec 9.5), non per lista di id: gli stessi
    filtri di GET /notifications, applicati a tutte le righe corrispondenti."""

    group_id: uuid.UUID | None = None
    receiver_id: uuid.UUID | None = None
    severity_min: Severity | None = None
    q: str | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None

    model_config = {"populate_by_name": True}


class BulkReadOut(BaseModel):
    marked_read: int


class StatsSummaryOut(BaseModel):
    total_unread: int
    by_severity: dict[str, int]
    by_group: list[dict]
    notifications_last_24h: int
    deliveries_dead: int
