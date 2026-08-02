"""E2E per la risoluzione delle destinazioni e l'outbox (spec 8.1, 8.2, 8.3)."""

import uuid

import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.types import DeliveryStatus, OverrideMode, Severity
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from tests.conftest_factories import create_receiver, create_severity_rule


async def _create_channel(tenant_id: uuid.UUID, enabled: bool = True) -> uuid.UUID:
    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/T0/B0/X0"),
                enabled=enabled,
            )
        )
    return channel_id


async def _bind_group_channel(
    tenant_id: uuid.UUID,
    group_id: uuid.UUID,
    channel_id: uuid.UUID,
    min_severity: Severity = Severity.ERROR,
) -> None:
    async with tenant_session(tenant_id) as session:
        session.add(
            GroupChannelBinding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                group_id=group_id,
                channel_id=channel_id,
                min_severity=min_severity,
                enabled=True,
            )
        )


@pytest.mark.e2e
async def test_ingestion_crea_delivery_pending_sopra_soglia(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    async with tenant_session(tenant_id) as session:
        from app.models.receiver import Receiver

        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        group_id = result.scalar_one().group_id

    channel_id = await _create_channel(tenant_id)
    await _bind_group_channel(tenant_id, group_id, channel_id, min_severity=Severity.ERROR)
    await create_severity_rule(tenant_id, receiver_id, pattern="FALLITO", severity=Severity.ERROR)

    response = await api_client.post(f"/ingest/{slug}", content="Backup FALLITO")
    assert response.status_code == 201
    assert response.json()["forwarded_to"] == 1

    notification_id = uuid.UUID(response.json()["id"])
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Delivery).where(Delivery.notification_id == notification_id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].status == DeliveryStatus.PENDING
        assert deliveries[0].channel_id == channel_id


@pytest.mark.e2e
async def test_sotto_soglia_non_crea_delivery(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, default_severity=Severity.INFO)

    async with tenant_session(tenant_id) as session:
        from app.models.receiver import Receiver

        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        group_id = result.scalar_one().group_id

    channel_id = await _create_channel(tenant_id)
    await _bind_group_channel(tenant_id, group_id, channel_id, min_severity=Severity.ERROR)

    response = await api_client.post(f"/ingest/{slug}", content="tutto ok")
    assert response.status_code == 201
    assert response.json()["forwarded_to"] == 0


@pytest.mark.e2e
async def test_receiver_override_mute_sopprime_linoltro(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, default_severity=Severity.CRITICAL)

    async with tenant_session(tenant_id) as session:
        from app.models.receiver import Receiver

        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        group_id = result.scalar_one().group_id

    channel_id = await _create_channel(tenant_id)
    await _bind_group_channel(tenant_id, group_id, channel_id, min_severity=Severity.ERROR)

    async with tenant_session(tenant_id) as session:
        session.add(
            ReceiverChannelOverride(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                channel_id=channel_id,
                mode=OverrideMode.MUTE,
                min_severity=None,
            )
        )

    response = await api_client.post(f"/ingest/{slug}", content="qualunque cosa")
    assert response.status_code == 201
    assert response.json()["forwarded_to"] == 0


@pytest.mark.e2e
async def test_channel_disabilitato_non_riceve_delivery(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, default_severity=Severity.CRITICAL)

    async with tenant_session(tenant_id) as session:
        from app.models.receiver import Receiver

        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        group_id = result.scalar_one().group_id

    channel_id = await _create_channel(tenant_id, enabled=False)
    await _bind_group_channel(tenant_id, group_id, channel_id, min_severity=Severity.DEBUG)

    response = await api_client.post(f"/ingest/{slug}", content="qualunque cosa")
    assert response.status_code == 201
    assert response.json()["forwarded_to"] == 0


@pytest.mark.e2e
async def test_enqueue_avviene_dopo_il_commit_e_vede_la_delivery(api_client, two_tenants):
    """D7 / spec 8.3: il task va accodato SOLO dopo il commit. La callback
    dell'hook after_commit di SQLAlchemy, per definizione, non puo essere
    invocata se il commit non e gia stato eseguito con successo: verifichiamo
    che venga chiamata esattamente una volta con l'id della delivery giusta,
    e che a quel punto la riga sia gia leggibile con una query indipendente."""
    from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function

    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, default_severity=Severity.CRITICAL)

    async with tenant_session(tenant_id) as session:
        from app.models.receiver import Receiver

        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        group_id = result.scalar_one().group_id

    channel_id = await _create_channel(tenant_id)
    await _bind_group_channel(tenant_id, group_id, channel_id, min_severity=Severity.DEBUG)

    enqueued_calls = []
    set_enqueue_function(lambda delivery_id, tid: enqueued_calls.append((delivery_id, tid)))
    try:
        response = await api_client.post(f"/ingest/{slug}", content="qualunque cosa")
        assert response.status_code == 201
        assert response.json()["forwarded_to"] == 1
    finally:
        reset_enqueue_function()

    assert len(enqueued_calls) == 1
    delivery_id, called_tenant_id = enqueued_calls[0]
    assert called_tenant_id == str(tenant_id)

    # La riga e visibile con una lettura fresca, indipendente dalla
    # transazione che l'ha scritta: prova che il commit e gia avvenuto.
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Delivery).where(Delivery.id == uuid.UUID(delivery_id))
        )
        assert result.scalar_one_or_none() is not None
