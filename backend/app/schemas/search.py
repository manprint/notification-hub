from datetime import datetime

from pydantic import BaseModel, Field

from app.db.types import NotificationStatus, Severity


class NotificationSearchFilters(BaseModel):
    query: str | None = Field(None, min_length=1, max_length=500)
    severity: list[Severity] | None = None
    status: NotificationStatus | None = None
    receiver_id: str | None = None
    received_after: datetime | None = None
    received_before: datetime | None = None
    archived: bool = False
    sort_by: str = Field("received_at", pattern="^(received_at|severity)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)


class NotificationSearchResult(BaseModel):
    id: str
    title: str
    content_preview: str
    severity: Severity
    status: NotificationStatus
    received_at: datetime
    score: float | None = None


class NotificationSearchResponse(BaseModel):
    results: list[NotificationSearchResult]
    total: int
    took_ms: int


class NotificationAggregation(BaseModel):
    severity: dict[str, int]
    status: dict[str, int]
    by_receiver: dict[str, int] | None = None
