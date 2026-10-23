"""E2E: un guasto DOPO il commit non deve far perdere l'idempotenza (spec 6.3, 8.3).

Il commit e il punto di non ritorno: la notifica e le sue delivery sono gia
scritte. Se l'accodamento o il salvataggio della risposta falliscono, il mittente
deve ricevere 201 e un retry con lo stesso X-Request-Id deve dare un replay, non
una seconda notifica.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.db.session import tenant_session
from app.db.types import Severity
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from tests.conftest_factories import create_receiver
from tests.e2e.test_outbound import _bind_group_channel, _create_channel


async def _receiver_con_canale(tenant_id: uuid.UUID, slug: str) -> uuid.UUID:
    receiver_id = await create_receiver(tenant_id, slug, default_severity=Severity.CRITICAL)
    async with tenant_session(tenant_id) as session:
        result = await session.execute(select(Receiver).where(Receiver.id == receiver_id))
        group_id = result.scalar_one().group_id
    channel_id = await _create_channel(tenant_id)
    await _bind_group_channel(tenant_id, group_id, channel_id, min_severity=Severity.DEBUG)
    return receiver_id


async def _conta_notifiche(tenant_id: uuid.UUID, receiver_id: uuid.UUID) -> int:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(func.count(Notification.id)).where(Notification.receiver_id == receiver_id)
        )
        return result.scalar_one()


async def _conta_delivery(tenant_id: uuid.UUID, notification_id: str) -> int:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(func.count(Delivery.id)).where(
                Delivery.notification_id == uuid.UUID(notification_id)
            )
        )
        return result.scalar_one()


@pytest.mark.e2e
async def test_broker_che_cade_dopo_il_commit_resta_201_e_il_retry_e_un_replay(
    api_client, two_tenants
):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await _receiver_con_canale(tenant_id, slug)
    request_id = f"cron-{uuid.uuid4().hex}"

    def _broker_giu(delivery_id: str, tid: str) -> None:
        raise ConnectionError("broker non raggiungibile")

    set_enqueue_function(_broker_giu)
    try:
        first = await api_client.post(
            f"/ingest/{slug}", content="backup", headers={"X-Request-Id": request_id}
        )
        second = await api_client.post(
            f"/ingest/{slug}", content="backup", headers={"X-Request-Id": request_id}
        )
    finally:
        reset_enqueue_function()

    # La notifica e' committata: il mittente non deve vedere un errore.
    assert first.status_code == 201
    body = first.json()
    assert body["forwarded_to"] == 1

    # Il retry con lo stesso X-Request-Id e' un replay, non una nuova notifica.
    assert second.status_code == 200
    assert second.headers["Idempotent-Replay"] == "true"
    assert second.json()["id"] == body["id"]

    assert await _conta_notifiche(tenant_id, receiver_id) == 1
    # La riga di delivery resta pending: la ripesca reconcile_deliveries (spec 8.3).
    assert await _conta_delivery(tenant_id, body["id"]) == 1


@pytest.mark.e2e
async def test_store_response_che_fallisce_dopo_il_commit_non_duplica_la_notifica(
    api_client, two_tenants, monkeypatch
):
    """Redis cade fra il commit e il salvataggio del replay: la risposta e' gia
    una 201, e il retry non deve creare un secondo doppione. La sentinella resta
    a `in elaborazione` fino alla scadenza, quindi il retry vede un 409."""
    from app.api import ingest as ingest_module
    from app.services import idempotency

    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await _receiver_con_canale(tenant_id, slug)
    request_id = f"cron-{uuid.uuid4().hex}"

    async def _redis_giu(*args, **kwargs):
        raise ConnectionError("redis non raggiungibile")

    monkeypatch.setattr(ingest_module, "store_response", _redis_giu)
    monkeypatch.setattr(idempotency, "IDEMPOTENCY_WAIT_SECONDS", 0.1)

    first = await api_client.post(
        f"/ingest/{slug}", content="backup", headers={"X-Request-Id": request_id}
    )
    assert first.status_code == 201

    second = await api_client.post(
        f"/ingest/{slug}", content="backup", headers={"X-Request-Id": request_id}
    )

    assert second.status_code == 409
    assert await _conta_notifiche(tenant_id, receiver_id) == 1
