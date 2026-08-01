from pydantic import BaseModel, Field

from app.db.types import Severity


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)


class GroupOut(BaseModel):
    id: str
    name: str
    description: str | None


class GroupChannelBindingCreate(BaseModel):
    channel_id: str
    min_severity: Severity
    enabled: bool = True


class GroupChannelBindingOut(BaseModel):
    id: str
    group_id: str
    channel_id: str
    min_severity: Severity
    enabled: bool


class ReceiverChannelOverrideCreate(BaseModel):
    channel_id: str
    mode: str = Field(pattern="^(override|disable)$")
    min_severity: Severity | None = None


class ReceiverChannelOverrideOut(BaseModel):
    id: str
    receiver_id: str
    channel_id: str
    mode: str
    min_severity: Severity | None
