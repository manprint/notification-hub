import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.types import UserRole, UserStatus


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
    # non str (vedi nota in schemas/group.py). group_ids non e un attributo
    # dell'ORM User: va valorizzato a posteriori dall'endpoint, come
    # ReceiverOut.rejected_last_24h.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    status: str
    last_login_at: datetime | None
    group_ids: list[uuid.UUID] = Field(default_factory=list)


class UserPatchIn(BaseModel):
    # UserRole/UserStatus e non str: un valore fuori dominio deve dare 422
    # dalla validazione, non una ValueError non gestita (cioe un 500) al
    # momento della conversione dentro l'endpoint.
    role: UserRole | None = None
    status: UserStatus | None = None
    # None = non toccare le associazioni; una lista (anche vuota) sostituisce
    # per intero l'insieme dei gruppi gestiti dall'utente.
    group_ids: list[uuid.UUID] | None = None


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role: UserRole
    group_ids: list[uuid.UUID] = Field(default_factory=list)


class InvitationIn(BaseModel):
    email: EmailStr
    role: UserRole


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
