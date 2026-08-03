"""Receiver e SeverityRule (spec 9.3): CRUD, rotate-slug, test-severity."""

import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin, require_member
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.models.receiver import Receiver
from app.models.severity_rule import SeverityRule
from app.models.tenant import Tenant
from app.schemas.receiver import (
    DeleteImpactOut,
    ReceiverCreate,
    ReceiverOut,
    ReceiverUpdate,
    SeverityRuleCreate,
    SeverityRuleOut,
    SeverityRuleUpdate,
    TestSeverityIn,
    TestSeverityOut,
)
from app.services.authz import accessible_group_ids, assert_group_access
from app.services.severity import InvalidPatternError, compile_pattern, resolve_severity

router = APIRouter(tags=["receivers"])

SLUG_LENGTH_BYTES = 16  # secrets.token_urlsafe(16) -> 22 caratteri (spec 4.2)


async def _get_receiver_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, receiver_id: uuid.UUID
) -> Receiver:
    result = await session.execute(
        select(Receiver).where(
            Receiver.id == receiver_id,
            Receiver.tenant_id == tenant_id,
        )
    )
    receiver = result.scalar_one_or_none()
    if receiver is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Receiver not found.",
        )
    return receiver


async def _assert_group_exists(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    from app.models.group import Group

    result = await session.execute(
        select(Group.id).where(Group.id == group_id, Group.tenant_id == tenant_id)
    )
    if result.scalar_one_or_none() is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Group not found.",
        )


async def _validate_max_body_bytes(
    session: AsyncSession, tenant_id: uuid.UUID, requested: int | None
) -> int:
    tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one()
    if requested is None:
        return tenant.max_body_bytes
    if requested > tenant.max_body_bytes:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail=f"max_body_bytes exceeds tenant cap of {tenant.max_body_bytes} bytes.",
        )
    return requested


@router.post("/groups/{group_id}/receivers", response_model=ReceiverOut, status_code=201)
async def create_receiver(
    group_id: uuid.UUID,
    body: ReceiverCreate,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    tenant_id = uuid.UUID(claims.tid)
    await _assert_group_exists(session, tenant_id, group_id)
    await assert_group_access(session, claims, group_id, write=True)
    max_body_bytes = await _validate_max_body_bytes(session, tenant_id, body.max_body_bytes)

    receiver = Receiver(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        group_id=group_id,
        slug=secrets.token_urlsafe(SLUG_LENGTH_BYTES),
        name=body.name,
        status="active",
        ingestion_module="http_raw",
        default_severity=body.default_severity,
        max_body_bytes=max_body_bytes,
        rate_limit_per_min=body.rate_limit_per_min,
    )
    session.add(receiver)
    await session.flush()
    return ReceiverOut.model_validate(receiver)


@router.get("/groups/{group_id}/receivers", response_model=list[ReceiverOut])
async def list_receivers(
    group_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverOut]:
    await assert_group_access(session, claims, group_id, write=False)
    result = await session.execute(
        select(Receiver)
        .where(
            Receiver.group_id == group_id,
            Receiver.tenant_id == uuid.UUID(claims.tid),
        )
        .order_by(Receiver.name.asc())
    )
    return [ReceiverOut.model_validate(r) for r in result.scalars().all()]


@router.get("/receivers", response_model=list[ReceiverOut])
async def list_all_receivers(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverOut]:
    """Tutti i receiver visibili al chiamante, per i selettori della UI che
    non partono da un gruppo (override per receiver nella pagina Canali)."""
    conditions = [Receiver.tenant_id == uuid.UUID(claims.tid)]
    allowed = await accessible_group_ids(session, claims)
    if allowed is not None:
        if not allowed:
            return []
        conditions.append(Receiver.group_id.in_(allowed))

    result = await session.execute(
        select(Receiver).where(*conditions).order_by(Receiver.name.asc())
    )
    return [ReceiverOut.model_validate(r) for r in result.scalars().all()]


@router.get("/receivers/{receiver_id}", response_model=ReceiverOut)
async def get_receiver(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    receiver = await _get_receiver_or_404(session, uuid.UUID(claims.tid), receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)
    out = ReceiverOut.model_validate(receiver)

    from app.core.redis import get_redis

    redis = await get_redis()
    rejected = await redis.get(f"ingest:rejected:{receiver.id}")
    out.rejected_last_24h = int(rejected) if rejected is not None else 0
    return out


@router.patch("/receivers/{receiver_id}", response_model=ReceiverOut)
async def update_receiver(
    receiver_id: uuid.UUID,
    body: ReceiverUpdate,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    if body.name is not None:
        receiver.name = body.name
    if body.status is not None:
        receiver.status = body.status
    if body.max_body_bytes is not None:
        receiver.max_body_bytes = await _validate_max_body_bytes(
            session, tenant_id, body.max_body_bytes
        )
    if body.rate_limit_per_min is not None:
        receiver.rate_limit_per_min = body.rate_limit_per_min
    if body.default_severity is not None:
        receiver.default_severity = body.default_severity

    await session.flush()
    return ReceiverOut.model_validate(receiver)


@router.delete("/receivers/{receiver_id}", status_code=204)
async def delete_receiver(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    receiver = await _get_receiver_or_404(session, uuid.UUID(claims.tid), receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)
    await session.delete(receiver)


@router.post("/receivers/{receiver_id}/rotate-slug", response_model=ReceiverOut)
async def rotate_slug(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    """Rigenera lo slug. Ad admin+ anche se il member puo creare receiver:
    rigenerare uno slug rompe gli script gia in produzione (spec 4.1)."""
    receiver = await _get_receiver_or_404(session, uuid.UUID(claims.tid), receiver_id)
    receiver.slug = secrets.token_urlsafe(SLUG_LENGTH_BYTES)
    await session.flush()
    return ReceiverOut.model_validate(receiver)


@router.get("/receivers/{receiver_id}/severity-rules", response_model=list[SeverityRuleOut])
async def list_severity_rules(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[SeverityRuleOut]:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    result = await session.execute(
        select(SeverityRule)
        .where(
            SeverityRule.receiver_id == receiver_id,
            SeverityRule.tenant_id == tenant_id,
        )
        .order_by(SeverityRule.priority.asc())
    )
    return [SeverityRuleOut.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/receivers/{receiver_id}/severity-rules", response_model=SeverityRuleOut, status_code=201
)
async def create_severity_rule(
    receiver_id: uuid.UUID,
    body: SeverityRuleCreate,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityRuleOut:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    try:
        compile_pattern(body.pattern, body.case_insensitive)
    except InvalidPatternError as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=f"Pattern not compilable by RE2: {exc}",
        ) from exc

    rule = SeverityRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        receiver_id=receiver_id,
        priority=body.priority,
        pattern=body.pattern,
        case_insensitive=body.case_insensitive,
        severity=body.severity,
        enabled=body.enabled,
    )
    session.add(rule)
    await session.flush()
    return SeverityRuleOut.model_validate(rule)


async def _get_rule_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> SeverityRule:
    result = await session.execute(
        select(SeverityRule).where(
            SeverityRule.id == rule_id,
            SeverityRule.tenant_id == tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Severity rule not found.",
        )
    return rule


@router.patch("/severity-rules/{rule_id}", response_model=SeverityRuleOut)
async def update_severity_rule(
    rule_id: uuid.UUID,
    body: SeverityRuleUpdate,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityRuleOut:
    tenant_id = uuid.UUID(claims.tid)
    rule = await _get_rule_or_404(session, tenant_id, rule_id)
    receiver = await _get_receiver_or_404(session, tenant_id, rule.receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    new_pattern = body.pattern if body.pattern is not None else rule.pattern
    new_case_insensitive = (
        body.case_insensitive if body.case_insensitive is not None else rule.case_insensitive
    )
    if body.pattern is not None or body.case_insensitive is not None:
        try:
            compile_pattern(new_pattern, new_case_insensitive)
        except InvalidPatternError as exc:
            raise Problem(
                status=422,
                type=PROBLEM_TYPES["validation_error"],
                title="Validation Error",
                detail=f"Pattern not compilable by RE2: {exc}",
            ) from exc

    if body.priority is not None:
        rule.priority = body.priority
    if body.pattern is not None:
        rule.pattern = body.pattern
    if body.case_insensitive is not None:
        rule.case_insensitive = body.case_insensitive
    if body.severity is not None:
        rule.severity = body.severity
    if body.enabled is not None:
        rule.enabled = body.enabled

    await session.flush()
    return SeverityRuleOut.model_validate(rule)


@router.delete("/severity-rules/{rule_id}", status_code=204)
async def delete_severity_rule(
    rule_id: uuid.UUID,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    tenant_id = uuid.UUID(claims.tid)
    rule = await _get_rule_or_404(session, tenant_id, rule_id)
    receiver = await _get_receiver_or_404(session, tenant_id, rule.receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)
    await session.delete(rule)


@router.post("/receivers/{receiver_id}/test-severity", response_model=TestSeverityOut)
async def test_severity(
    receiver_id: uuid.UUID,
    body: TestSeverityIn,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> TestSeverityOut:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    rules_result = await session.execute(
        select(SeverityRule).where(
            SeverityRule.receiver_id == receiver_id,
            SeverityRule.tenant_id == tenant_id,
            SeverityRule.enabled.is_(True),
        )
    )
    rules = list(rules_result.scalars().all())

    resolution = resolve_severity(
        header_severity=body.header_severity,
        query_severity=None,
        rules=rules,
        content_sample=body.content,
        default_severity=receiver.default_severity,
    )

    return TestSeverityOut(
        severity=resolution.severity,
        source=resolution.source.value,
        matched_rule_id=resolution.matched_rule_id,
        matched_pattern=resolution.matched_pattern,
    )


@router.get("/groups/{group_id}/delete-impact", response_model=DeleteImpactOut)
async def group_delete_impact(
    group_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeleteImpactOut:
    """Preflight per la cancellazione di un gruppo (spec 9.3): conteggi reali
    di receiver, notifiche e delivery che verrebbero eliminati in cascata."""
    from app.models.delivery import Delivery
    from app.models.notification import Notification

    tenant_id = uuid.UUID(claims.tid)
    await assert_group_access(session, claims, group_id, write=False)

    receivers_result = await session.execute(
        select(Receiver.id).where(Receiver.group_id == group_id, Receiver.tenant_id == tenant_id)
    )
    receiver_ids = [row[0] for row in receivers_result.all()]

    if not receiver_ids:
        return DeleteImpactOut(receivers=0, notifications=0, deliveries=0)

    notifications_result = await session.execute(
        select(Notification.id).where(
            Notification.receiver_id.in_(receiver_ids), Notification.tenant_id == tenant_id
        )
    )
    notification_ids = [row[0] for row in notifications_result.all()]

    deliveries_count = 0
    if notification_ids:
        deliveries_result = await session.execute(
            select(Delivery.id).where(
                Delivery.notification_id.in_(notification_ids), Delivery.tenant_id == tenant_id
            )
        )
        deliveries_count = len(deliveries_result.all())

    return DeleteImpactOut(
        receivers=len(receiver_ids),
        notifications=len(notification_ids),
        deliveries=deliveries_count,
    )
