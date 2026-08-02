"""Test del task Celery dispatch_delivery (spec 8.2): macchina a stati e
gestione degli esiti del webhook. Il task viene chiamato direttamente (non
via broker): Celery permette di invocare un task come funzione normale."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.types import DeliveryStatus, Severity
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.tasks.delivery import dispatch_delivery
from tests.conftest_factories import create_receiver

WEBHOOK_URL = "https://hooks.slack.com/services/T0/B0/X0"


async def _setup_delivery(
    tenant_id: uuid.UUID, status: str = "pending"
) -> tuple[uuid.UUID, uuid.UUID]:
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    channel_id = uuid.uuid4()
    notification_id = uuid.uuid4()
    delivery_id = uuid.uuid4()

    async with tenant_session(tenant_id) as session:
        # flush esplicito fra ogni insert: l'ordinamento automatico dello unit
        # of work non va dato per scontato quando le entita non sono legate
        # da relationship() ORM, solo da ForeignKey a livello di colonna.
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret(WEBHOOK_URL),
                enabled=True,
            )
        )
        await session.flush()

        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                storage_backend="inline",
                content="Backup FALLITO",
                storage_key=None,
                content_preview="Backup FALLITO",
                content_size=len("Backup FALLITO"),
                content_normalized=False,
                severity=Severity.ERROR,
                severity_source="receiver_default",
                status="unread",
                received_at=datetime.now(UTC),
                source_ip=None,
                meta={},
            )
        )
        await session.flush()

        session.add(
            Delivery(
                id=delivery_id,
                tenant_id=tenant_id,
                notification_id=notification_id,
                channel_id=channel_id,
                status=status,
                attempts=0,
                next_attempt_at=datetime.now(UTC),
            )
        )
        await session.flush()

    return delivery_id, channel_id


@pytest.mark.integration
@respx.mock
async def test_2xx_marca_sent(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.SENT
        assert delivery.sent_at is not None
        assert delivery.response_code == 200


@pytest.mark.integration
@respx.mock
async def test_4xx_non_429_marca_dead_senza_retry(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, channel_id = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(410))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.attempts == 0  # morta subito, non e un retry
        channel = await session.get(DeliveryChannel, channel_id)
        assert channel.last_error is not None


@pytest.mark.integration
@respx.mock
async def test_429_ripianifica_rispettando_retry_after(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "120"}))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 0


@pytest.mark.integration
@respx.mock
async def test_5xx_incrementa_attempts_e_ripianifica(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(503))

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.FAILED
        assert delivery.attempts == 1
        assert delivery.next_attempt_at is not None


@pytest.mark.integration
@respx.mock
async def test_5xx_dopo_5_tentativi_diventa_dead(two_tenants):
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id)
    respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(503))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        delivery.attempts = 4

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.DEAD
        assert delivery.attempts == 5


@pytest.mark.integration
async def test_delivery_gia_sent_viene_ignorata(two_tenants):
    """Idempotenza del task: una delivery non piu pending/failed (per esempio
    perche un altro worker l'ha gia consumata) non viene rilavorata."""
    tenant_id, _ = two_tenants
    delivery_id, _ = await _setup_delivery(tenant_id, status="sent")

    dispatch_delivery(str(delivery_id), str(tenant_id))

    async with tenant_session(tenant_id) as session:
        delivery = await session.get(Delivery, delivery_id)
        assert delivery.status == DeliveryStatus.SENT
        assert delivery.attempts == 0
