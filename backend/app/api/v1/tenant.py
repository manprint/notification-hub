"""Impostazioni del tenant (spec 9.3)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_owner
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.models.group import Group
from app.models.receiver import Receiver
from app.models.tenant import Tenant
from app.schemas.tenant import TenantOut, TenantUpdate
from app.services.tenant_lock import lock_tenant_settings

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
async def get_tenant(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db, scope="function"),  # noqa: B008
) -> TenantOut:
    result = await session.execute(select(Tenant).where(Tenant.id == uuid.UUID(claims.tid)))
    tenant = result.scalar_one()
    return TenantOut.model_validate(tenant)


UNLIMITED_WHEN_NULL = (
    "max_notifications_per_day",
    "max_storage_bytes",
    "retention_days",
    "audit_retention_days",
)


@router.patch("", response_model=TenantOut)
async def update_tenant(
    body: TenantUpdate,
    claims: AccessClaims = Depends(require_owner),  # noqa: B008
    session: AsyncSession = Depends(db, scope="function"),  # noqa: B008
) -> TenantOut:
    tenant_id = uuid.UUID(claims.tid)
    # Lock NO KEY UPDATE: un receiver creato o modificato in parallelo legge il cap
    # sotto lo stesso lock, altrimenti il controllo qui sotto non vedrebbe il suo
    # valore. Non fermano le ingestion del tenant, che prendono solo FOR KEY SHARE.
    tenant = await lock_tenant_settings(session, tenant_id)

    if body.max_body_bytes is not None and body.max_body_bytes < tenant.max_body_bytes:
        # Il nome di un receiver e' unico solo nel suo gruppo: il client riceve id e
        # gruppo per distinguerli, e la chiave della lista non puo' essere il nome.
        conflicting_result = await session.execute(
            select(Receiver.id, Receiver.name, Group.name, Receiver.max_body_bytes)
            .join(
                Group,
                and_(Group.id == Receiver.group_id, Group.tenant_id == tenant_id),
            )
            .where(
                Receiver.tenant_id == tenant_id,
                Receiver.max_body_bytes > body.max_body_bytes,
            )
        )
        conflicting = [
            {
                "id": str(receiver_id),
                "name": name,
                "group_name": group_name,
                "max_body_bytes": max_body_bytes,
            }
            for receiver_id, name, group_name, max_body_bytes in conflicting_result.all()
        ]
        if conflicting:
            raise Problem(
                status=409,
                type=PROBLEM_TYPES["conflict"],
                title="Conflict",
                detail="Some receivers have a higher max_body_bytes than requested.",
                extra={"conflicting_receivers": conflicting},
            )

    if body.name is not None:
        tenant.name = body.name
    if body.max_body_bytes is not None:
        tenant.max_body_bytes = body.max_body_bytes
    # Quote e ritenzioni: NULL = illimitata (spec 4.1), quindi un null esplicito
    # e' un valore da scrivere, non un campo da ignorare. Senza questa
    # distinzione una quota impostata una volta non tornava piu' illimitata.
    for field in UNLIMITED_WHEN_NULL:
        if field in body.model_fields_set:
            setattr(tenant, field, getattr(body, field))

    await session.flush()
    return TenantOut.model_validate(tenant)
