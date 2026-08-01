import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import UserOut, UserPatchIn

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[UserOut]:
    result = await session.execute(select(User).where(User.tenant_id == uuid.UUID(claims.tid)))
    users = result.scalars().all()
    return [UserOut.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(  # noqa: B008
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
async def update_user(  # noqa: B008
    user_id: str,
    body: UserPatchIn,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
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

    if user.role == UserRole.OWNER and body.role and body.role != UserRole.OWNER:
        owners_result = await session.execute(
            select(User).where(
                User.tenant_id == uuid.UUID(claims.tid),
                User.role == UserRole.OWNER,
            )
        )
        owners = owners_result.scalars().all()
        if len(owners) == 1:
            raise Problem(
                status=409,
                type=PROBLEM_TYPES["last_owner"],
                title="Conflict",
                detail="Cannot remove last owner of tenant.",
            )

    if body.role:
        user.role = UserRole(body.role)
    if body.status:
        user.status = UserStatus(body.status)

    await session.flush()
    return UserOut.model_validate(user)


@router.post("/{user_id}/deactivate", status_code=204)
async def deactivate_user(  # noqa: B008
    user_id: str,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
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

    if user.role == UserRole.OWNER:
        owners_result = await session.execute(
            select(User).where(
                User.tenant_id == uuid.UUID(claims.tid),
                User.role == UserRole.OWNER,
            )
        )
        owners = owners_result.scalars().all()
        if len(owners) == 1:
            raise Problem(
                status=409,
                type=PROBLEM_TYPES["last_owner"],
                title="Conflict",
                detail="Cannot deactivate last owner of tenant.",
            )

    user.status = UserStatus.DISABLED
    await session.flush()
