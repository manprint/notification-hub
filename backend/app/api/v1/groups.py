import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.models.binding import GroupChannelBinding
from app.models.group import Group
from app.schemas.group import (
    GroupChannelBindingCreate,
    GroupChannelBindingOut,
    GroupCreate,
    GroupOut,
    GroupUpdate,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupOut])
async def list_groups(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[GroupOut]:
    result = await session.execute(select(Group).where(Group.tenant_id == uuid.UUID(claims.tid)))
    groups = result.scalars().all()
    return [GroupOut.model_validate(g) for g in groups]


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(
    body: GroupCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> GroupOut:
    tenant_id = uuid.UUID(claims.tid)

    group = Group(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
    )
    session.add(group)
    await session.flush()
    return GroupOut.model_validate(group)


@router.get("/{group_id}", response_model=GroupOut)
async def get_group(
    group_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> GroupOut:
    result = await session.execute(
        select(Group).where(
            Group.id == uuid.UUID(group_id),
            Group.tenant_id == uuid.UUID(claims.tid),
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Group not found.",
        )
    return GroupOut.model_validate(group)


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: str,
    body: GroupUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> GroupOut:
    result = await session.execute(
        select(Group).where(
            Group.id == uuid.UUID(group_id),
            Group.tenant_id == uuid.UUID(claims.tid),
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Group not found.",
        )

    if body.name is not None:
        group.name = body.name
    if body.description is not None:
        group.description = body.description

    await session.flush()
    return GroupOut.model_validate(group)


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    confirm: str = Query(...),  # noqa: B008
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    """Cascade su receiver, notifiche, delivery e oggetti MinIO (via trigger),
    confermata digitando il nome esatto del gruppo (spec 9.3): niente
    cancellazioni accidentali di dati che nessuna UI ripristina."""
    result = await session.execute(
        select(Group).where(
            Group.id == uuid.UUID(group_id),
            Group.tenant_id == uuid.UUID(claims.tid),
        )
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Group not found.",
        )
    if confirm != group.name:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="confirm must match the exact group name.",
        )
    await session.delete(group)


@router.get("/{group_id}/channels", response_model=list[GroupChannelBindingOut])
async def list_group_channels(
    group_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[GroupChannelBindingOut]:
    result = await session.execute(
        select(GroupChannelBinding).where(
            GroupChannelBinding.group_id == uuid.UUID(group_id),
            GroupChannelBinding.tenant_id == uuid.UUID(claims.tid),
        )
    )
    bindings = result.scalars().all()
    return [GroupChannelBindingOut.model_validate(b) for b in bindings]


@router.post("/{group_id}/channels", response_model=GroupChannelBindingOut, status_code=201)
async def bind_group_channel(
    group_id: str,
    body: GroupChannelBindingCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> GroupChannelBindingOut:
    tenant_id = uuid.UUID(claims.tid)

    binding = GroupChannelBinding(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        group_id=uuid.UUID(group_id),
        channel_id=uuid.UUID(body.channel_id),
        min_severity=body.min_severity,
        enabled=body.enabled,
    )
    session.add(binding)
    await session.flush()
    return GroupChannelBindingOut.model_validate(binding)


@router.delete("/{group_id}/channels/{channel_id}", status_code=204)
async def unbind_group_channel(
    group_id: str,
    channel_id: str,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    result = await session.execute(
        select(GroupChannelBinding).where(
            GroupChannelBinding.group_id == uuid.UUID(group_id),
            GroupChannelBinding.channel_id == uuid.UUID(channel_id),
            GroupChannelBinding.tenant_id == uuid.UUID(claims.tid),
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Binding not found.",
        )
    await session.delete(binding)
