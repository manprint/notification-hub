from datetime import datetime

from pydantic import BaseModel

from app.db.types import NotificationStatus, Severity


class NotificationOut(BaseModel):
    id: str
    title: str
    content_preview: str
    severity: Severity
    status: NotificationStatus
    received_at: datetime
    archived_at: datetime | None = None


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    total: int
    unread_count: int


class MarkReadRequest(BaseModel):
    notification_ids: list[str]


class MarkUnreadRequest(BaseModel):
    notification_ids: list[str]


class ArchiveRequest(BaseModel):
    notification_ids: list[str]
