"""DeliveryChannel e i binding di gruppo/receiver (spec 9.4)."""

import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin, require_member
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_webhook
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import DeliveryStatus, OverrideMode, Severity
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.schemas.delivery import (
    DeliveryChannelCreate,
    DeliveryChannelOut,
    DeliveryChannelTestOut,
    DeliveryChannelUpdate,
    DeliveryOut,
)
from app.schemas.group import (
    GroupChannelBindingOut,
    GroupChannelBindingUpdate,
    ReceiverChannelOverrideCreate,
    ReceiverChannelOverrideOut,
    ReceiverChannelOverrideUpdate,
)
from app.services.authz import accessible_group_ids, assert_group_access

router = APIRouter(tags=["channels"])

DELIVERY_PREVIEW_CHARS = 160


def _validate_webhook_url(webhook_url: str) -> None:
    parsed = urlparse(webhook_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Webhook URL must be an absolute http(s) URL.",
        )
    allowlist = get_settings().webhook_host_allowlist_list
    if allowlist and parsed.hostname not in allowlist:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=f"Webhook host '{parsed.hostname}' is not in the allowlist.",
        )


def _channel_out(channel: DeliveryChannel) -> DeliveryChannelOut:
    hint = mask_webhook(decrypt_secret(channel.webhook_url))
    return DeliveryChannelOut(
        id=str(channel.id),
        name=channel.name,
        type=channel.type,
        webhook_hint=hint,
        enabled=channel.enabled,
        last_success_at=channel.last_success_at.isoformat() if channel.last_success_at else None,
        last_error_at=channel.last_error_at.isoformat() if channel.last_error_at else None,
        last_error=channel.last_error,
    )


async def _get_channel_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, channel_id: uuid.UUID
) -> DeliveryChannel:
    result = await session.execute(
        select(DeliveryChannel).where(
            DeliveryChannel.id == channel_id,
            DeliveryChannel.tenant_id == tenant_id,
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Delivery channel not found.",
        )
    return channel


async def _get_receiver_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, receiver_id: uuid.UUID
) -> Receiver:
    result = await session.execute(
        select(Receiver).where(Receiver.id == receiver_id, Receiver.tenant_id == tenant_id)
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


@router.get("/channels", response_model=list[DeliveryChannelOut])
async def list_channels(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[DeliveryChannelOut]:
    result = await session.execute(
        select(DeliveryChannel)
        .where(DeliveryChannel.tenant_id == uuid.UUID(claims.tid))
        .order_by(DeliveryChannel.name.asc())
    )
    return [_channel_out(ch) for ch in result.scalars().all()]


@router.post("/channels", response_model=DeliveryChannelOut, status_code=201)
async def create_channel(
    body: DeliveryChannelCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    _validate_webhook_url(body.webhook_url)
    channel = DeliveryChannel(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(claims.tid),
        name=body.name,
        type=body.type,
        webhook_url=encrypt_secret(body.webhook_url),
        enabled=body.enabled,
    )
    session.add(channel)
    await session.flush()
    return _channel_out(channel)


@router.get("/channels/{channel_id}", response_model=DeliveryChannelOut)
async def get_channel(
    channel_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    channel = await _get_channel_or_404(session, uuid.UUID(claims.tid), channel_id)
    return _channel_out(channel)


@router.patch("/channels/{channel_id}", response_model=DeliveryChannelOut)
async def update_channel(
    channel_id: uuid.UUID,
    body: DeliveryChannelUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    channel = await _get_channel_or_404(session, uuid.UUID(claims.tid), channel_id)
    if body.name is not None:
        channel.name = body.name
    if body.webhook_url is not None:
        _validate_webhook_url(body.webhook_url)
        channel.webhook_url = encrypt_secret(body.webhook_url)
    if body.enabled is not None:
        channel.enabled = body.enabled
    await session.flush()
    return _channel_out(channel)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    """Rimuove prima binding, override e storico delivery del canale: le FK
    verso delivery_channels non hanno ON DELETE, quindi senza questa pulizia
    la cancellazione di un canale in uso usciva come 500 dal database."""
    tenant_id = uuid.UUID(claims.tid)
    channel = await _get_channel_or_404(session, tenant_id, channel_id)

    for model in (GroupChannelBinding, ReceiverChannelOverride, Delivery):
        await session.execute(
            sql_delete(model).where(
                model.channel_id == channel_id,
                model.tenant_id == tenant_id,
            )
        )
    await session.flush()
    await session.delete(channel)


@router.post("/channels/{channel_id}/test", response_model=DeliveryChannelTestOut)
async def test_channel(
    channel_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelTestOut:
    channel = await _get_channel_or_404(session, uuid.UUID(claims.tid), channel_id)
    webhook_url = decrypt_secret(channel.webhook_url)

    payload = {"text": f"NotifyHub: messaggio di prova per il canale '{channel.name}'."}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        return DeliveryChannelTestOut(sent=True, detail=f"HTTP {response.status_code}")
    except httpx.HTTPError as exc:
        return DeliveryChannelTestOut(sent=False, detail=str(exc))


@router.put("/groups/{group_id}/channels/{channel_id}", response_model=GroupChannelBindingOut)
async def update_group_channel_binding(
    group_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: GroupChannelBindingUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> GroupChannelBindingOut:
    result = await session.execute(
        select(GroupChannelBinding).where(
            GroupChannelBinding.group_id == group_id,
            GroupChannelBinding.channel_id == channel_id,
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
    if body.min_severity is not None:
        binding.min_severity = body.min_severity
    if body.enabled is not None:
        binding.enabled = body.enabled
    await session.flush()
    return GroupChannelBindingOut.model_validate(binding)


@router.get("/receivers/{receiver_id}/channels", response_model=list[ReceiverChannelOverrideOut])
async def list_receiver_overrides(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverChannelOverrideOut]:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == receiver_id,
            ReceiverChannelOverride.tenant_id == tenant_id,
        )
    )
    return [ReceiverChannelOverrideOut.model_validate(o) for o in result.scalars().all()]


def _override_min_severity(mode: OverrideMode, min_severity: Severity | None) -> Severity | None:
    """mode=override senza soglia e uno stato che il worker non sa gestire
    (outbound_resolver asserisce min_severity non NULL): va rifiutato qui."""
    if mode == OverrideMode.OVERRIDE and min_severity is None:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="min_severity is required when mode is 'override'.",
        )
    return min_severity if mode == OverrideMode.OVERRIDE else None


@router.post(
    "/receivers/{receiver_id}/channels", response_model=ReceiverChannelOverrideOut, status_code=201
)
async def create_receiver_override(
    receiver_id: uuid.UUID,
    body: ReceiverChannelOverrideCreate,
    response: Response,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverChannelOverrideOut:
    """Idempotente sulla coppia (receiver, canale): un secondo salvataggio
    aggiorna l'override esistente e risponde 200. Prima violava il vincolo di
    unicita e usciva come 500, cosi come un receiver o un canale inesistente
    (violazione di FK)."""
    tenant_id = uuid.UUID(claims.tid)
    min_severity = _override_min_severity(body.mode, body.min_severity)

    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)
    await _get_channel_or_404(session, tenant_id, body.channel_id)

    existing_result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == receiver_id,
            ReceiverChannelOverride.channel_id == body.channel_id,
            ReceiverChannelOverride.tenant_id == tenant_id,
        )
    )
    override = existing_result.scalar_one_or_none()
    if override is not None:
        override.mode = body.mode
        override.min_severity = min_severity
        response.status_code = 200
    else:
        override = ReceiverChannelOverride(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            receiver_id=receiver_id,
            channel_id=body.channel_id,
            mode=body.mode,
            min_severity=min_severity,
        )
        session.add(override)
    await session.flush()
    return ReceiverChannelOverrideOut.model_validate(override)


@router.put(
    "/receivers/{receiver_id}/channels/{channel_id}", response_model=ReceiverChannelOverrideOut
)
async def update_receiver_override(
    receiver_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: ReceiverChannelOverrideUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverChannelOverrideOut:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == receiver_id,
            ReceiverChannelOverride.channel_id == channel_id,
            ReceiverChannelOverride.tenant_id == tenant_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Override not found.",
        )

    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    mode = body.mode if body.mode is not None else override.mode
    min_severity = body.min_severity if body.min_severity is not None else override.min_severity
    override.mode = mode
    override.min_severity = _override_min_severity(mode, min_severity)

    await session.flush()
    return ReceiverChannelOverrideOut.model_validate(override)


@router.delete("/receivers/{receiver_id}/channels/{channel_id}", status_code=204)
async def delete_receiver_override(
    receiver_id: uuid.UUID,
    channel_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == receiver_id,
            ReceiverChannelOverride.channel_id == channel_id,
            ReceiverChannelOverride.tenant_id == tenant_id,
        )
    )
    override = result.scalar_one_or_none()
    if override is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Override not found.",
        )
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)
    await session.delete(override)


def _delivery_out(
    delivery: Delivery,
    channel_name: str | None,
    receiver_name: str,
    notification: Notification,
) -> DeliveryOut:
    return DeliveryOut(
        id=str(delivery.id),
        notification_id=str(delivery.notification_id),
        channel_id=str(delivery.channel_id),
        channel_name=channel_name or "(canale rimosso)",
        receiver_name=receiver_name,
        severity=notification.severity,
        content_preview=notification.content_preview[:DELIVERY_PREVIEW_CHARS],
        received_at=notification.received_at,
        status=delivery.status,
        attempts=delivery.attempts,
        next_attempt_at=delivery.next_attempt_at,
        locked_at=delivery.locked_at,
        response_code=delivery.response_code,
        last_error=delivery.last_error,
        sent_at=delivery.sent_at,
    )


_DELIVERY_ROW = (Delivery, DeliveryChannel.name, Receiver.name, Notification, Receiver.group_id)


@router.get("/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    status_filter: DeliveryStatus | None = Query(default=None, alias="status"),  # noqa: B008
    channel_id: uuid.UUID | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=100, ge=1, le=500),  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[DeliveryOut]:
    """Storico degli inoltri verso i canali, per diagnosticare i fallimenti
    (spec 9.4). Ogni riga porta con se il canale di destinazione, il receiver
    e l'anteprima della notifica inoltrata: senza, la pagina mostrava solo
    stato e contatori, illeggibili."""
    tenant_id = uuid.UUID(claims.tid)
    conditions = [Delivery.tenant_id == tenant_id]
    if status_filter is not None:
        conditions.append(Delivery.status == status_filter)
    if channel_id is not None:
        conditions.append(Delivery.channel_id == channel_id)

    allowed = await accessible_group_ids(session, claims)
    if allowed is not None:
        if not allowed:
            return []
        conditions.append(Receiver.group_id.in_(allowed))

    result = await session.execute(
        select(*_DELIVERY_ROW)
        .join(Notification, Notification.id == Delivery.notification_id)
        .join(Receiver, Receiver.id == Notification.receiver_id)
        .outerjoin(DeliveryChannel, DeliveryChannel.id == Delivery.channel_id)
        .where(*conditions)
        .order_by(Notification.received_at.desc(), Delivery.next_attempt_at.desc())
        .limit(limit)
    )

    return [
        _delivery_out(delivery, channel_name, receiver_name, notification)
        for delivery, channel_name, receiver_name, notification, _group_id in result.all()
    ]


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryOut)
async def retry_delivery(
    delivery_id: uuid.UUID,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryOut:
    """Ri-accoda una delivery `dead`: azzera attempts, last_error e locked_at
    (spec 4.3, macchina a stati: dead -> pending solo per questa via)."""
    from datetime import UTC, datetime

    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(*_DELIVERY_ROW)
        .join(Notification, Notification.id == Delivery.notification_id)
        .join(Receiver, Receiver.id == Notification.receiver_id)
        .outerjoin(DeliveryChannel, DeliveryChannel.id == Delivery.channel_id)
        .where(Delivery.id == delivery_id, Delivery.tenant_id == tenant_id)
    )
    row = result.first()
    if row is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Delivery not found.",
        )
    delivery, channel_name, receiver_name, notification, group_id = row
    await assert_group_access(session, claims, group_id, write=True)

    if delivery.status != DeliveryStatus.DEAD:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="Only a dead delivery can be retried.",
        )

    delivery.status = DeliveryStatus.PENDING
    delivery.attempts = 0
    delivery.last_error = None
    delivery.locked_at = None
    delivery.next_attempt_at = datetime.now(UTC)
    await session.flush()

    from app.tasks.enqueue import register_after_commit_enqueue

    register_after_commit_enqueue(session, [(str(delivery.id), claims.tid)])

    return _delivery_out(delivery, channel_name, receiver_name, notification)
