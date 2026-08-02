"""DeliveryChannel e i binding di gruppo/receiver (spec 9.4)."""

import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin, require_member
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_webhook
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.db.types import DeliveryStatus, OverrideMode
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.schemas.delivery import (
    DeliveryChannelCreate,
    DeliveryChannelOut,
    DeliveryChannelTestOut,
    DeliveryChannelUpdate,
    DeliveryOut,
)
from app.schemas.group import (
    GroupChannelBindingUpdate,
    ReceiverChannelOverrideCreate,
    ReceiverChannelOverrideOut,
    ReceiverChannelOverrideUpdate,
)

router = APIRouter(tags=["channels"])


def _validate_webhook_host(webhook_url: str) -> None:
    host = urlparse(webhook_url).hostname or ""
    allowlist = get_settings().webhook_host_allowlist_list
    if allowlist and host not in allowlist:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=f"Webhook host '{host}' is not in the allowlist.",
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
    session: AsyncSession, tenant_id: uuid.UUID, channel_id: str
) -> DeliveryChannel:
    result = await session.execute(
        select(DeliveryChannel).where(
            DeliveryChannel.id == uuid.UUID(channel_id),
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


@router.get("/channels", response_model=list[DeliveryChannelOut])
async def list_channels(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[DeliveryChannelOut]:
    result = await session.execute(
        select(DeliveryChannel).where(DeliveryChannel.tenant_id == uuid.UUID(claims.tid))
    )
    return [_channel_out(ch) for ch in result.scalars().all()]


@router.post("/channels", response_model=DeliveryChannelOut, status_code=201)
async def create_channel(
    body: DeliveryChannelCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    _validate_webhook_host(body.webhook_url)
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
    channel_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    channel = await _get_channel_or_404(session, uuid.UUID(claims.tid), channel_id)
    return _channel_out(channel)


@router.patch("/channels/{channel_id}", response_model=DeliveryChannelOut)
async def update_channel(
    channel_id: str,
    body: DeliveryChannelUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryChannelOut:
    channel = await _get_channel_or_404(session, uuid.UUID(claims.tid), channel_id)
    if body.name is not None:
        channel.name = body.name
    if body.webhook_url is not None:
        _validate_webhook_host(body.webhook_url)
        channel.webhook_url = encrypt_secret(body.webhook_url)
    if body.enabled is not None:
        channel.enabled = body.enabled
    await session.flush()
    return _channel_out(channel)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: str,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    channel = await _get_channel_or_404(session, uuid.UUID(claims.tid), channel_id)
    await session.delete(channel)


@router.post("/channels/{channel_id}/test", response_model=DeliveryChannelTestOut)
async def test_channel(
    channel_id: str,
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


@router.put("/groups/{group_id}/channels/{channel_id}", response_model=None, status_code=200)
async def update_group_channel_binding(
    group_id: str,
    channel_id: str,
    body: GroupChannelBindingUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> dict:
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
    if body.min_severity is not None:
        binding.min_severity = body.min_severity
    if body.enabled is not None:
        binding.enabled = body.enabled
    await session.flush()
    return {
        "id": str(binding.id),
        "group_id": str(binding.group_id),
        "channel_id": str(binding.channel_id),
        "min_severity": binding.min_severity,
        "enabled": binding.enabled,
    }


@router.get("/receivers/{receiver_id}/channels", response_model=list[ReceiverChannelOverrideOut])
async def list_receiver_overrides(
    receiver_id: str,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverChannelOverrideOut]:
    result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == uuid.UUID(receiver_id),
            ReceiverChannelOverride.tenant_id == uuid.UUID(claims.tid),
        )
    )
    return [ReceiverChannelOverrideOut.model_validate(o) for o in result.scalars().all()]


@router.post(
    "/receivers/{receiver_id}/channels", response_model=ReceiverChannelOverrideOut, status_code=201
)
async def create_receiver_override(
    receiver_id: str,
    body: ReceiverChannelOverrideCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverChannelOverrideOut:
    if body.mode == "override" and body.min_severity is None:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="min_severity is required when mode is 'override'.",
        )

    override = ReceiverChannelOverride(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(claims.tid),
        receiver_id=uuid.UUID(receiver_id),
        channel_id=uuid.UUID(body.channel_id),
        mode=body.mode,
        min_severity=body.min_severity if body.mode == "override" else None,
    )
    session.add(override)
    await session.flush()
    return ReceiverChannelOverrideOut.model_validate(override)


@router.put(
    "/receivers/{receiver_id}/channels/{channel_id}", response_model=ReceiverChannelOverrideOut
)
async def update_receiver_override(
    receiver_id: str,
    channel_id: str,
    body: ReceiverChannelOverrideUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverChannelOverrideOut:
    result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == uuid.UUID(receiver_id),
            ReceiverChannelOverride.channel_id == uuid.UUID(channel_id),
            ReceiverChannelOverride.tenant_id == uuid.UUID(claims.tid),
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
    if body.mode is not None:
        override.mode = OverrideMode(body.mode)
    if body.min_severity is not None or override.mode == "mute":
        override.min_severity = body.min_severity if override.mode == "override" else None
    await session.flush()
    return ReceiverChannelOverrideOut.model_validate(override)


@router.delete("/receivers/{receiver_id}/channels/{channel_id}", status_code=204)
async def delete_receiver_override(
    receiver_id: str,
    channel_id: str,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.receiver_id == uuid.UUID(receiver_id),
            ReceiverChannelOverride.channel_id == uuid.UUID(channel_id),
            ReceiverChannelOverride.tenant_id == uuid.UUID(claims.tid),
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
    await session.delete(override)


def _delivery_out(delivery: Delivery) -> DeliveryOut:
    return DeliveryOut(
        id=str(delivery.id),
        notification_id=str(delivery.notification_id),
        channel_id=str(delivery.channel_id),
        status=delivery.status,
        attempts=delivery.attempts,
        next_attempt_at=delivery.next_attempt_at,
        locked_at=delivery.locked_at,
        response_code=delivery.response_code,
        last_error=delivery.last_error,
        sent_at=delivery.sent_at,
    )


@router.get("/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    status_filter: DeliveryStatus | None = Query(default=None, alias="status"),  # noqa: B008
    channel_id: str | None = Query(default=None),  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[DeliveryOut]:
    """Storico inoltri, per diagnosticare i fallimenti (spec 9.4)."""
    conditions = [Delivery.tenant_id == uuid.UUID(claims.tid)]
    if status_filter is not None:
        conditions.append(Delivery.status == status_filter)
    if channel_id is not None:
        conditions.append(Delivery.channel_id == uuid.UUID(channel_id))

    result = await session.execute(
        select(Delivery).where(*conditions).order_by(Delivery.next_attempt_at.desc())
    )
    return [_delivery_out(d) for d in result.scalars().all()]


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryOut)
async def retry_delivery(
    delivery_id: str,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeliveryOut:
    """Ri-accoda una delivery `dead`: azzera attempts, last_error e locked_at
    (spec 4.3, macchina a stati: dead -> pending solo per questa via)."""
    from datetime import UTC, datetime

    result = await session.execute(
        select(Delivery).where(
            Delivery.id == uuid.UUID(delivery_id), Delivery.tenant_id == uuid.UUID(claims.tid)
        )
    )
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Delivery not found.",
        )
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

    return _delivery_out(delivery)
