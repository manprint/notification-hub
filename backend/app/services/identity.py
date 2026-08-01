from dataclasses import dataclass

from sqlalchemy import select

from app.db.session import auth_session
from app.models.invitation import Invitation
from app.models.refresh_token import RefreshToken
from app.models.user import User


@dataclass
class UserIdentity:
    id: str
    tenant_id: str
    email: str
    password_hash: str
    role: str
    status: str


@dataclass
class RefreshTokenIdentity:
    id: str
    tenant_id: str
    user_id: str
    family_id: str
    expires_at: str
    revoked_at: str | None


@dataclass
class InvitationIdentity:
    id: str
    tenant_id: str
    email: str
    role: str
    expires_at: str
    accepted_at: str | None
    token_hash: str


async def find_user_by_email(email: str) -> UserIdentity | None:
    async with auth_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            return None
        return UserIdentity(
            id=str(user.id),
            tenant_id=str(user.tenant_id),
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            status=user.status,
        )


async def find_refresh_token(token_hash: str) -> RefreshTokenIdentity | None:
    async with auth_session() as session:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        token = result.scalar_one_or_none()
        if not token:
            return None
        return RefreshTokenIdentity(
            id=str(token.id),
            tenant_id=str(token.tenant_id),
            user_id=str(token.user_id),
            family_id=str(token.family_id),
            expires_at=token.expires_at.isoformat(),
            revoked_at=token.revoked_at.isoformat() if token.revoked_at else None,
        )


async def find_invitation(token_hash: str) -> InvitationIdentity | None:
    async with auth_session() as session:
        result = await session.execute(
            select(Invitation).where(Invitation.token_hash == token_hash)
        )
        inv = result.scalar_one_or_none()
        if not inv:
            return None
        return InvitationIdentity(
            id=str(inv.id),
            tenant_id=str(inv.tenant_id),
            email=inv.email,
            role=inv.role,
            expires_at=inv.expires_at.isoformat(),
            accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None,
            token_hash=inv.token_hash,
        )
