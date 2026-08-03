"""Autorizzazione a grana di gruppo sui receiver: owner e admin hanno CRUD su
tutti i gruppi, member CRUD solo sui gruppi a cui e associato, viewer solo
lettura sui gruppi a cui e associato."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import UserRole
from app.models.user_group_membership import UserGroupMembership


def has_full_group_access(claims: AccessClaims) -> bool:
    """owner e admin vedono e gestiscono tutti i gruppi del tenant."""
    return claims.role in (UserRole.OWNER, UserRole.ADMIN)


async def accessible_group_ids(
    session: AsyncSession, claims: AccessClaims
) -> list[uuid.UUID] | None:
    """Gruppi visibili al chiamante. None = nessun vincolo (owner/admin).

    Una lista vuota significa che l'utente non e associato a nessun gruppo e
    quindi non deve vedere niente: i chiamanti devono distinguere `None` da
    `[]`, non usare un semplice test di verita.
    """
    if has_full_group_access(claims):
        return None

    result = await session.execute(
        select(UserGroupMembership.group_id).where(
            UserGroupMembership.user_id == uuid.UUID(claims.sub),
            UserGroupMembership.tenant_id == uuid.UUID(claims.tid),
        )
    )
    return [row[0] for row in result.all()]


async def assert_group_access(
    session: AsyncSession,
    claims: AccessClaims,
    group_id: uuid.UUID,
    *,
    write: bool,
) -> None:
    if has_full_group_access(claims):
        return

    if write and claims.role == UserRole.VIEWER:
        raise Problem(
            status=403,
            type=PROBLEM_TYPES["forbidden"],
            title="Forbidden",
            detail="Viewers have read-only access.",
        )

    result = await session.execute(
        select(UserGroupMembership.id).where(
            UserGroupMembership.user_id == uuid.UUID(claims.sub),
            UserGroupMembership.group_id == group_id,
            UserGroupMembership.tenant_id == uuid.UUID(claims.tid),
        )
    )
    if result.scalar_one_or_none() is None:
        raise Problem(
            status=403,
            type=PROBLEM_TYPES["forbidden"],
            title="Forbidden",
            detail="Not a member of this receiver group.",
        )
