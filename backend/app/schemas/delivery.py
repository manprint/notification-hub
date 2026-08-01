from pydantic import BaseModel, Field

from app.db.types import ChannelType


class DeliveryChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: ChannelType
    webhook_url: bytes
    enabled: bool = True


class DeliveryChannelOut(BaseModel):
    id: str
    name: str
    type: ChannelType
    webhook_url: bytes
    enabled: bool
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error: str | None = None
