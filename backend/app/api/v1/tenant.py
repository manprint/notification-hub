"""Impostazioni del tenant (spec 9.3)."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_owner
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.models.receiver import Receiver
from app.models.tenant import Tenant
from app.schemas.tenant import TenantOut, TenantUpdate

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantOut)
async def get_tenant(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> TenantOut:
    result = await session.execute(select(Tenant).where(Tenant.id == uuid.UUID(claims.tid)))
    tenant = result.scalar_one()
    return TenantOut.model_validate(tenant)


@router.patch("", response_model=TenantOut)
async def update_tenant(
    body: TenantUpdate,
    claims: AccessClaims = Depends(require_owner),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> TenantOut:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one()

    if body.max_body_bytes is not None and body.max_body_bytes < tenant.max_body_bytes:
        conflicting_result = await session.execute(
            select(Receiver.name, Receiver.max_body_bytes).where(
                Receiver.tenant_id == tenant_id,
                Receiver.max_body_bytes > body.max_body_bytes,
            )
        )
        conflicting = [
            {"name": name, "max_body_bytes": max_body_bytes}
            for name, max_body_bytes in conflicting_result.all()
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
    if body.max_notifications_per_day is not None:
        tenant.max_notifications_per_day = body.max_notifications_per_day
    if body.max_storage_bytes is not None:
        tenant.max_storage_bytes = body.max_storage_bytes
    if body.retention_days is not None:
        tenant.retention_days = body.retention_days
    if body.audit_retention_days is not None:
        tenant.audit_retention_days = body.audit_retention_days

    await session.flush()
    return TenantOut.model_validate(tenant)
