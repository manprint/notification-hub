import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import UserRole, UserStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import UserOut, UserPatchIn

router = APIRouter(prefix="/users", tags=["users"])


async def _assert_not_last_owner(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """SELECT ... FOR UPDATE sulla riga del tenant per serializzare due
    rimozioni concorrenti dell'ultimo owner (spec 4.1): senza il lock, due
    richieste simultanee potrebbero entrambe vedere 2 owner e passare
    entrambe, lasciando il tenant senza nessuno."""
    await session.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update())

    owners_result = await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.role == UserRole.OWNER)
    )
    if len(owners_result.scalars().all()) <= 1:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["last_owner"],
            title="Conflict",
            detail="Cannot remove or demote the last owner of the tenant.",
        )


@router.get("", response_model=list[UserOut])
async def list_users(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[UserOut]:
    result = await session.execute(select(User).where(User.tenant_id == uuid.UUID(claims.tid)))
    users = result.scalars().all()
    return [UserOut.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> UserOut:
    result = await session.execute(
        select(User).where(
            User.id == uuid.UUID(user_id),
            User.tenant_id == uuid.UUID(claims.tid),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="User not found.",
        )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserPatchIn,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> UserOut:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="User not found.",
        )

    if user.role == UserRole.OWNER and body.role and body.role != UserRole.OWNER:
        await _assert_not_last_owner(session, tenant_id)

    if body.role:
        user.role = UserRole(body.role)
    if body.status:
        user.status = UserStatus(body.status)

    await session.flush()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=204)
async def remove_user(
    user_id: str,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    """Rimozione (spec 9.2). Disabilita l'utente invece di eliminare la riga:
    refresh_tokens e invitations referenziano users.id senza ON DELETE, e la
    disabilitazione preserva comunque l'audit (last_login_at, created_at)."""
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="User not found.",
        )

    if user.role == UserRole.OWNER:
        await _assert_not_last_owner(session, tenant_id)

    user.status = UserStatus.DISABLED
    await session.flush()
