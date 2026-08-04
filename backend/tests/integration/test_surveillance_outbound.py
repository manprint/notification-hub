"""L'allarme di assenza fino al webhook, e le regole di instradamento su di esso.

Le notifiche della sorveglianza nascono in un job sincrono e passano da un gemello
sincrono dell'instradamento (`create_deliveries_for_notification_sync`). E' la
parte piu' a rischio di tutta la funzione: se quel gemello divergesse dal percorso
dell'ingestion, l'allarme piu' importante sarebbe l'unico consegnato con regole
diverse da tutti gli altri messaggi.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select, update

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.types import DeliveryStatus, OverrideMode, Severity, SeveritySource
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from app.tasks.maintenance import check_expected_schedules
from tests.conftest_factories import create_group, create_receiver

WEBHOOK_URL = "https://hooks.slack.com/services/T0/B0/SURVEILLANCE"


async def _canale(tenant_id: uuid.UUID) -> uuid.UUID:
    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name=f"Slack {uuid.uuid4().hex[:6]}",
                type="slack",
                webhook_url=encrypt_secret(WEBHOOK_URL),
                enabled=True,
            )
        )
    return channel_id


async def _binding(
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


async def _receiver_sorvegliato_in_ritardo(tenant_id: uuid.UUID, group_id: uuid.UUID):
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(
                expected_every_seconds=86400,
                expected_grace_seconds=1800,
                missing_severity=Severity.CRITICAL,
                last_notification_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
    return receiver_id


async def _deliveries(tenant_id: uuid.UUID, receiver_id: uuid.UUID) -> list[Delivery]:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Delivery)
            .join(Notification, Notification.id == Delivery.notification_id)
            .where(Notification.receiver_id == receiver_id)
        )
        return list(result.scalars().all())


def _esegui_job() -> list[tuple[str, str]]:
    accodate: list[tuple[str, str]] = []
    set_enqueue_function(lambda delivery_id, tid: accodate.append((delivery_id, tid)))
    try:
        check_expected_schedules()
    finally:
        reset_enqueue_function()
    return accodate


@pytest.mark.integration
async def test_override_mute_zittisce_anche_lassenza(two_tenants):
    """Un canale messo in mute su questo receiver deve restare muto anche per
    l'allarme di assenza: e' la stessa regola dell'ingestion, e l'operatore che ha
    silenziato un canale non si aspetta un'eccezione proprio sul job piu' rumoroso."""
    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Mute {uuid.uuid4().hex[:6]}")
    channel_id = await _canale(tenant_id)
    await _binding(tenant_id, group_id, channel_id, Severity.INFO)
    receiver_id = await _receiver_sorvegliato_in_ritardo(tenant_id, group_id)

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

    _esegui_job()

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Notification).where(Notification.receiver_id == receiver_id)
        )
        assert len(list(result.scalars().all())) == 1  # l'assenza c'e' in dashboard...
    assert await _deliveries(tenant_id, receiver_id) == []  # ...ma non sul canale


@pytest.mark.integration
async def test_override_alza_la_soglia_solo_su_questo_receiver(two_tenants):
    """Override con soglia piu' alta della severity dell'assenza: nessuna consegna,
    anche se il binding del gruppo la lascerebbe passare."""
    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Override {uuid.uuid4().hex[:6]}")
    channel_id = await _canale(tenant_id)
    await _binding(tenant_id, group_id, channel_id, Severity.INFO)
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(
                expected_every_seconds=86400,
                expected_grace_seconds=1800,
                missing_severity=Severity.WARNING,
                last_notification_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        session.add(
            ReceiverChannelOverride(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                channel_id=channel_id,
                mode=OverrideMode.OVERRIDE,
                min_severity=Severity.CRITICAL,
            )
        )

    _esegui_job()

    assert await _deliveries(tenant_id, receiver_id) == []


@pytest.mark.integration
async def test_canale_disabilitato_non_riceve_lassenza(two_tenants):
    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Spento {uuid.uuid4().hex[:6]}")
    channel_id = await _canale(tenant_id)
    await _binding(tenant_id, group_id, channel_id, Severity.INFO)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(DeliveryChannel).where(DeliveryChannel.id == channel_id).values(enabled=False)
        )
    receiver_id = await _receiver_sorvegliato_in_ritardo(tenant_id, group_id)

    _esegui_job()

    assert await _deliveries(tenant_id, receiver_id) == []


@pytest.mark.integration
@respx.mock
async def test_lassenza_arriva_davvero_al_webhook(two_tenants):
    """Il giro completo: job -> notifica sintetica -> outbox -> worker -> webhook.
    Prova che il messaggio inoltrato si formatta senza durata ne' exit code, che
    su una notifica scritta dal server sono NULL."""
    from app.tasks.delivery import dispatch_delivery

    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Consegna {uuid.uuid4().hex[:6]}")
    channel_id = await _canale(tenant_id)
    await _binding(tenant_id, group_id, channel_id, Severity.ERROR)
    await _receiver_sorvegliato_in_ritardo(tenant_id, group_id)

    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    accodate = _esegui_job()
    assert len(accodate) == 1

    delivery_id, tid = accodate[0]
    dispatch_delivery(delivery_id, tid)

    assert route.called
    inviato = route.calls[0].request.content.decode()
    assert "nessun invio" in inviato

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Delivery).where(Delivery.id == uuid.UUID(delivery_id))
        )
        delivery = result.scalar_one()
    assert delivery.status == DeliveryStatus.SENT


@pytest.mark.integration
@respx.mock
async def test_anche_la_ripresa_arriva_al_webhook_se_la_soglia_lo_permette(two_tenants):
    """La ripresa e' `info`: passa solo dove la soglia del canale la ammette. Se
    non passasse mai, l'allarme resterebbe aperto su Slack senza chiusura."""
    from app.tasks.delivery import dispatch_delivery

    tenant_id, _ = two_tenants
    group_id = await create_group(tenant_id, f"Ripresa {uuid.uuid4().hex[:6]}")
    channel_id = await _canale(tenant_id)
    await _binding(tenant_id, group_id, channel_id, Severity.INFO)
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)

    allarme = datetime.now(UTC) - timedelta(hours=3)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(
                expected_every_seconds=86400,
                expected_grace_seconds=1800,
                missing_severity=Severity.CRITICAL,
                missing_alerted_at=allarme,
                last_notification_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )

    route = respx.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
    accodate = _esegui_job()
    assert len(accodate) == 1

    dispatch_delivery(*accodate[0])
    assert route.called
    assert "ha ripreso a inviare" in route.calls[0].request.content.decode()

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Notification).where(Notification.receiver_id == receiver_id)
        )
        notifiche = list(result.scalars().all())
    assert [n.severity_source for n in notifiche] == [SeveritySource.RECOVERED]
