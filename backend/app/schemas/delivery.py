from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import ChannelType, DeliveryStatus, Severity


class DeliveryChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: ChannelType
    webhook_url: str = Field(min_length=1)
    enabled: bool = True


class DeliveryChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    webhook_url: str | None = None
    enabled: bool | None = None


class DeliveryChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: ChannelType
    webhook_hint: str
    enabled: bool
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error: str | None = None


class DeliveryChannelTestOut(BaseModel):
    sent: bool
    detail: str


class DeliveryOut(BaseModel):
    """Costruito a mano dal router (non via model_validate): status e un
    enum Python, channel_id/notification_id/id sono UUID che vanno resi
    stringa esplicitamente per l'output diagnostico (spec 9.4).

    channel_name, receiver_name, severity, content_preview e received_at
    vengono dalla join: la riga deve dire da sola quale notifica e stata
    inoltrata e verso dove, altrimenti la pagina Consegne e illeggibile.
    """

    id: str
    notification_id: str
    channel_id: str
    channel_name: str
    receiver_name: str
    severity: Severity
    content_preview: str
    received_at: datetime
    status: DeliveryStatus
    attempts: int
    next_attempt_at: datetime
    locked_at: datetime | None
    response_code: int | None
    last_error: str | None
    sent_at: datetime | None
