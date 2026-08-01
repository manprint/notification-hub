import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import (
    AccessClaims,
    create_access_token,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.db.session import tenant_session
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginIn,
    LogoutIn,
    MeOut,
    RefreshIn,
    TokenPairOut,
)
from app.services.identity import find_refresh_token, find_user_by_email
from app.services.ratelimit import sliding_window_hit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPairOut, status_code=200)
async def login(body: LoginIn) -> TokenPairOut:
    rate_limit_key = f"login_attempts:{body.email}"
    rate_limit = await sliding_window_hit(rate_limit_key, 5, 900)

    if not rate_limit.allowed:
        raise Problem(
            status=429,
            type=PROBLEM_TYPES["rate_limited"],
            title="Too Many Requests",
            detail="Too many login attempts. Please try again later.",
        )

    user_identity = await find_user_by_email(body.email)

    if not user_identity:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid credentials.",
        )

    if not verify_password(body.password, user_identity.password_hash):
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid credentials.",
        )

    if user_identity.status != "active":
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid credentials.",
        )

    import uuid

    async with tenant_session(uuid.UUID(user_identity.tenant_id)) as session:
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == user_identity.tenant_id)
        )
        tenant = tenant_result.scalar_one()

        if tenant.status != "active":
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Invalid credentials.",
            )

        user_result = await session.execute(select(User).where(User.id == user_identity.id))
        user = user_result.scalar_one()
        user.last_login_at = datetime.utcnow()  # type: ignore[assignment]

        refresh_plain, refresh_hash = new_refresh_token()
        family_id_val = user_identity.id

        refresh_token_row = RefreshToken(
            tenant_id=user_identity.tenant_id,
            user_id=user_identity.id,
            token_hash=refresh_hash,
            jti=str(uuid.uuid4()),
            family_id=family_id_val,
            expires_at=datetime.utcnow(),
            revoked_at=None,
            user_agent=None,
            ip=None,
        )
        session.add(refresh_token_row)
        await session.flush()

        access_token, expires_in = create_access_token(
            user_identity.id, user_identity.tenant_id, user_identity.role
        )

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_plain,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenPairOut, status_code=200)
async def refresh(body: RefreshIn) -> TokenPairOut:
    refresh_token_identity = await find_refresh_token(hash_token(body.refresh_token))

    if not refresh_token_identity:
        raise Problem(
            status=401,
            type=PROBLEM_TYPES["unauthorized"],
            title="Unauthorized",
            detail="Invalid refresh token.",
        )

    async with tenant_session(uuid.UUID(refresh_token_identity.tenant_id)) as session:
        refresh_token_row = await session.get(RefreshToken, refresh_token_identity.id)

        if refresh_token_row is None or refresh_token_row.revoked_at is not None:
            if refresh_token_row is not None and refresh_token_row.family_id:
                refresh_result = await session.execute(
                    select(RefreshToken).where(
                        RefreshToken.family_id == refresh_token_row.family_id
                    )
                )
                family_tokens = refresh_result.scalars().all()
                for token in family_tokens:
                    token.revoked_at = datetime.utcnow()

            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Refresh token revoked or invalid.",
            )

        user_result = await session.execute(
            select(User).where(User.id == refresh_token_identity.user_id)
        )
        user = user_result.scalar_one()

        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == refresh_token_identity.tenant_id)
        )
        tenant = tenant_result.scalar_one()

        if user.status != "active" or tenant.status != "active":
            raise Problem(
                status=401,
                type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="User or tenant inactive.",
            )

        old_family_id = refresh_token_row.family_id
        refresh_token_row.revoked_at = datetime.utcnow()

        refresh_plain, refresh_hash = new_refresh_token()
        new_refresh_token_row = RefreshToken(
            tenant_id=refresh_token_identity.tenant_id,
            user_id=refresh_token_identity.user_id,
            token_hash=refresh_hash,
            jti=str(uuid.uuid4()),
            family_id=old_family_id,
            expires_at=datetime.utcnow(),
            revoked_at=None,
            user_agent=None,
            ip=None,
        )
        session.add(new_refresh_token_row)
        await session.flush()

        access_token, expires_in = create_access_token(str(user.id), str(tenant.id), user.role)

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_plain,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
    )


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutIn,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    if body.revoke_all:
        refresh_result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == uuid.UUID(claims.sub),
                RefreshToken.tenant_id == uuid.UUID(claims.tid),
                RefreshToken.revoked_at.is_(None),
            )
        )
        tokens = refresh_result.scalars().all()
        for token in tokens:
            token.revoked_at = datetime.utcnow()
    else:
        refresh_result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == uuid.UUID(claims.sub),
                RefreshToken.tenant_id == uuid.UUID(claims.tid),
                RefreshToken.jti == body.jti,
            )
        )
        refresh_row: RefreshToken | None = refresh_result.scalar_one_or_none()
        if refresh_row is not None:
            refresh_row.revoked_at = datetime.utcnow()

    await session.flush()


@router.get("/me", response_model=MeOut)
async def me(  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> MeOut:
    user_result = await session.execute(select(User).where(User.id == claims.sub))
    user = user_result.scalar_one()

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == claims.tid))
    tenant = tenant_result.scalar_one()

    return MeOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
    )
