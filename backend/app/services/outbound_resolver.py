"""Risoluzione delle destinazioni di inoltro e creazione dell'outbox (spec 8.1, 8.2)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.types import SEVERITY_ORDER, DeliveryStatus, OverrideMode, Severity
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery


def select_target_channels(
    *,
    bindings: Sequence[GroupChannelBinding],
    overrides_by_channel: dict[uuid.UUID, ReceiverChannelOverride],
    channels_by_id: dict[uuid.UUID, DeliveryChannel],
    severity: Severity,
) -> list[uuid.UUID]:
    """Quali canali devono ricevere questa notifica (spec 8.1): mute, override
    della soglia, soglia del binding, canale disabilitato.

    Funzione pura, senza sessione: la usano sia l'ingestion (async) sia il job di
    sorveglianza (sync). Le query e gli insert sono diversi nei due mondi, la
    regola di instradamento deve restare una sola.
    """
    targets: list[uuid.UUID] = []
    for binding in bindings:
        override = overrides_by_channel.get(binding.channel_id)
        if override is not None and override.mode == OverrideMode.MUTE:
            continue

        if override is not None and override.mode == OverrideMode.OVERRIDE:
            # Garantito non-NULL dalla validazione a livello di API in
            # creazione/modifica dell'override (mode=override richiede
            # min_severity), non dal database.
            assert override.min_severity is not None
            threshold = override.min_severity
        else:
            threshold = binding.min_severity

        if SEVERITY_ORDER[severity] < SEVERITY_ORDER[threshold]:
            continue

        channel = channels_by_id.get(binding.channel_id)
        if channel is None or not channel.enabled:
            continue

        targets.append(channel.id)
    return targets


async def create_deliveries_for_notification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    receiver_id: uuid.UUID,
    notification_id: uuid.UUID,
    severity: Severity,
) -> list[uuid.UUID]:
    """Algoritmo della spec 8.1: per ogni GroupChannelBinding abilitato del
    gruppo, applica l'eventuale ReceiverChannelOverride, poi crea una
    Delivery `pending` se la severity supera la soglia. Va chiamato nella
    STESSA transazione in cui e stata scritta la Notification (spec 8.2):
    il chiamante e app/api/ingest.py, subito dopo persist_notification.
    """
    bindings_result = await session.execute(
        select(GroupChannelBinding).where(
            GroupChannelBinding.tenant_id == tenant_id,
            GroupChannelBinding.group_id == group_id,
            GroupChannelBinding.enabled.is_(True),
        )
    )
    bindings = bindings_result.scalars().all()
    if not bindings:
        return []

    overrides_result = await session.execute(
        select(ReceiverChannelOverride).where(
            ReceiverChannelOverride.tenant_id == tenant_id,
            ReceiverChannelOverride.receiver_id == receiver_id,
        )
    )
    overrides_by_channel = {o.channel_id: o for o in overrides_result.scalars().all()}

    channel_ids = [b.channel_id for b in bindings]
    channels_result = await session.execute(
        select(DeliveryChannel).where(
            DeliveryChannel.tenant_id == tenant_id, DeliveryChannel.id.in_(channel_ids)
        )
    )
    channels_by_id = {c.id: c for c in channels_result.scalars().all()}

    targets = select_target_channels(
        bindings=bindings,
        overrides_by_channel=overrides_by_channel,
        channels_by_id=channels_by_id,
        severity=severity,
    )

    created_ids = _add_deliveries(
        session,
        tenant_id=tenant_id,
        notification_id=notification_id,
        channel_ids=targets,
    )
    if created_ids:
        await session.flush()

    return created_ids


def _add_deliveries(
    session: AsyncSession | Session,
    *,
    tenant_id: uuid.UUID,
    notification_id: uuid.UUID,
    channel_ids: Sequence[uuid.UUID],
) -> list[uuid.UUID]:
    """Righe di outbox `pending`, senza flush: lo fa il chiamante, che sa se la
    sua sessione e' sincrona o asincrona."""
    now = datetime.now(UTC)
    created_ids: list[uuid.UUID] = []
    for channel_id in channel_ids:
        delivery_id = uuid.uuid4()
        session.add(
            Delivery(
                id=delivery_id,
                tenant_id=tenant_id,
                notification_id=notification_id,
                channel_id=channel_id,
                status=DeliveryStatus.PENDING,
                attempts=0,
                next_attempt_at=now,
            )
        )
        created_ids.append(delivery_id)
    return created_ids


def create_deliveries_for_notification_sync(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    receiver_id: uuid.UUID,
    notification_id: uuid.UUID,
    severity: Severity,
) -> list[uuid.UUID]:
    """Gemello sincrono per il worker Celery: stessa regola di instradamento
    (`select_target_channels`), sessione sincrona.

    Serve alle notifiche che nascono dentro un job e non da una richiesta HTTP:
    quelle della sorveglianza dell'attesa devono raggiungere i canali esattamente
    come le altre, altrimenti l'allarme piu' importante sarebbe l'unico a non
    partire.
    """
    bindings = (
        session.execute(
            select(GroupChannelBinding).where(
                GroupChannelBinding.tenant_id == tenant_id,
                GroupChannelBinding.group_id == group_id,
                GroupChannelBinding.enabled.is_(True),
            )
        )
        .scalars()
        .all()
    )
    if not bindings:
        return []

    overrides_by_channel = {
        o.channel_id: o
        for o in session.execute(
            select(ReceiverChannelOverride).where(
                ReceiverChannelOverride.tenant_id == tenant_id,
                ReceiverChannelOverride.receiver_id == receiver_id,
            )
        )
        .scalars()
        .all()
    }

    channels_by_id = {
        c.id: c
        for c in session.execute(
            select(DeliveryChannel).where(
                DeliveryChannel.tenant_id == tenant_id,
                DeliveryChannel.id.in_([b.channel_id for b in bindings]),
            )
        )
        .scalars()
        .all()
    }

    targets = select_target_channels(
        bindings=bindings,
        overrides_by_channel=overrides_by_channel,
        channels_by_id=channels_by_id,
        severity=severity,
    )
    created_ids = _add_deliveries(
        session,
        tenant_id=tenant_id,
        notification_id=notification_id,
        channel_ids=targets,
    )
    if created_ids:
        session.flush()
    return created_ids
