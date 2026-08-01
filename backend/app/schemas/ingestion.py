from pydantic import BaseModel, Field


class NotificationIngest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(max_length=1048576)
    severity: str | None = None
    metadata: dict | None = None


class NotificationIngestResponse(BaseModel):
    notification_id: str
    status: str = "enqueued"
