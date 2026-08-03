import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RegisterIn(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=12)


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    revoke_all: bool = False
    jti: str | None = None


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    tenant_id: str
    tenant_name: str


class UserOut(BaseModel):
    # model_validate(user) su un oggetto ORM richiede uuid.UUID sui campi id,
    # non str (vedi nota in schemas/group.py).
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    status: str
    last_login_at: datetime | None


class UserPatchIn(BaseModel):
    role: str | None = None
    status: str | None = None


class InvitationIn(BaseModel):
    email: EmailStr
    role: str


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    expires_at: datetime
    invite_url: str
    email_sent: bool


class InvitationAcceptIn(BaseModel):
    token: str
    password: str = Field(min_length=12)


class InvitationSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
