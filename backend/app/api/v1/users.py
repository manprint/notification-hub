import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims, hash_password
from app.db.types import UserRole, UserStatus
from app.models.group import Group
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_group_membership import UserGroupMembership
from app.schemas.auth import UserCreateIn, UserOut, UserPatchIn
from app.services.identity import find_user_by_email

router = APIRouter(prefix="/users", tags=["users"])


async def _assert_not_last_owner(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """SELECT ... FOR UPDATE sulla riga del tenant per serializzare due
    rimozioni concorrenti dell'ultimo owner (spec 4.1): senza il lock, due
    richieste simultanee potrebbero entrambe vedere 2 owner e passare
    entrambe, lasciando il tenant senza nessuno.

    Conta solo gli owner ATTIVI: un owner disabilitato non puo accedere, e
    lasciarlo contare permetteva di disabilitare l'ultimo owner utilizzabile.
    """
    await session.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update())

    owners_result = await session.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.role == UserRole.OWNER,
            User.status == UserStatus.ACTIVE,
        )
    )
    if len(owners_result.scalars().all()) <= 1:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["last_owner"],
            title="Conflict",
            detail="Cannot remove or demote the last owner of the tenant.",
        )


def _assert_can_grant_owner(claims: AccessClaims, role: UserRole | None) -> None:
    """Solo un owner puo creare o promuovere un altro owner: altrimenti un
    admin puo autopromuoversi (o promuovere un complice) e superare ogni
    vincolo riservato al ruolo owner."""
    if role == UserRole.OWNER and claims.role != UserRole.OWNER:
        raise Problem(
            status=403,
            type=PROBLEM_TYPES["forbidden"],
            title="Forbidden",
            detail="Only an owner can grant the owner role.",
        )


async def _revoke_refresh_tokens(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for token in result.scalars().all():
        token.revoked_at = now


async def _assert_groups_exist(
    session: AsyncSession, tenant_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> None:
    if not group_ids:
        return
    result = await session.execute(
        select(Group.id).where(Group.tenant_id == tenant_id, Group.id.in_(group_ids))
    )
    found = {row[0] for row in result.all()}
    missing = set(group_ids) - found
    if missing:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=f"Unknown group_ids: {', '.join(str(g) for g in missing)}.",
        )


async def _group_ids_for_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await session.execute(
        select(UserGroupMembership.group_id).where(
            UserGroupMembership.tenant_id == tenant_id,
            UserGroupMembership.user_id == user_id,
        )
    )
    return [row[0] for row in result.all()]


async def _replace_user_groups(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    group_ids: list[uuid.UUID],
) -> None:
    await _assert_groups_exist(session, tenant_id, group_ids)
    existing = await session.execute(
        select(UserGroupMembership).where(
            UserGroupMembership.tenant_id == tenant_id,
            UserGroupMembership.user_id == user_id,
        )
    )
    for membership in existing.scalars().all():
        await session.delete(membership)
    await session.flush()

    for group_id in group_ids:
        session.add(
            UserGroupMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                group_id=group_id,
            )
        )
    await session.flush()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateIn,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> UserOut:
    """Creazione diretta (email + password specificate dall'admin), in
    alternativa al flusso di invito via email: l'utente risultante e gia
    attivo, senza bisogno di accettare un invito."""
    _assert_can_grant_owner(claims, body.role)
    existing = await find_user_by_email(body.email)
    if existing is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="Email already registered.",
        )

    tenant_id = uuid.UUID(claims.tid)
    await _assert_groups_exist(session, tenant_id, body.group_ids)

    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=body.email,
        password_hash=password_hash,
        role=UserRole(body.role),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()

    for group_id in body.group_ids:
        session.add(
            UserGroupMembership(
                id=uuid.uuid4(), tenant_id=tenant_id, user_id=user.id, group_id=group_id
            )
        )
    await session.flush()

    out = UserOut.model_validate(user)
    out.group_ids = body.group_ids
    return out


@router.get("", response_model=list[UserOut])
async def list_users(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[UserOut]:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(select(User).where(User.tenant_id == tenant_id))
    users = result.scalars().all()

    memberships_result = await session.execute(
        select(UserGroupMembership.user_id, UserGroupMembership.group_id).where(
            UserGroupMembership.tenant_id == tenant_id
        )
    )
    groups_by_user: dict[uuid.UUID, list[uuid.UUID]] = {}
    for user_id, group_id in memberships_result.all():
        groups_by_user.setdefault(user_id, []).append(group_id)

    outs = []
    for u in users:
        out = UserOut.model_validate(u)
        out.group_ids = groups_by_user.get(u.id, [])
        outs.append(out)
    return outs


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> UserOut:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
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
    out = UserOut.model_validate(user)
    out.group_ids = await _group_ids_for_user(session, tenant_id, user.id)
    return out


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserPatchIn,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> UserOut:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="User not found.",
        )

    _assert_can_grant_owner(claims, body.role)

    demoting = body.role is not None and body.role != UserRole.OWNER
    disabling = body.status is not None and body.status != UserStatus.ACTIVE
    # Disabilitare l'ultimo owner lo escludeva dal login lasciando il tenant
    # senza owner utilizzabili: stesso vincolo del cambio di ruolo.
    if user.role == UserRole.OWNER and user.status == UserStatus.ACTIVE and (demoting or disabling):
        await _assert_not_last_owner(session, tenant_id)

    if body.role is not None:
        user.role = body.role
    if body.status is not None:
        user.status = body.status
    if body.group_ids is not None:
        await _replace_user_groups(session, tenant_id, user.id, body.group_ids)

    await session.flush()
    out = UserOut.model_validate(user)
    out.group_ids = await _group_ids_for_user(session, tenant_id, user.id)
    return out


@router.delete("/{user_id}", status_code=204)
async def remove_user(
    user_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    """Rimozione (spec 9.2). Disabilita l'utente invece di eliminare la riga:
    refresh_tokens e invitations referenziano users.id senza ON DELETE, e la
    disabilitazione preserva comunque l'audit (last_login_at, created_at)."""
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="User not found.",
        )

    if user.role == UserRole.OWNER and user.status == UserStatus.ACTIVE:
        await _assert_not_last_owner(session, tenant_id)

    user.status = UserStatus.DISABLED
    # I refresh token restano validi fino alla scadenza e rigenererebbero un
    # access token per un utente ormai disabilitato: vanno revocati subito.
    await _revoke_refresh_tokens(session, tenant_id, user.id)
    await session.flush()
