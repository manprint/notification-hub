"""E2E: lo stato che l'ingestion lascia sul receiver (spec 9.1, 10.1).

Il contatore degli invii rifiutati ha una finestra di 24 ore fissa; il battito
di sorveglianza (`last_notification_at`) non arretra mai.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.redis import get_redis
from app.db.session import tenant_session
from app.db.types import ReceiverStatus
from app.models.receiver import Receiver
from tests.conftest_factories import create_receiver


@pytest.mark.e2e
async def test_contatore_rifiuti_non_slitta_a_ogni_invio_rifiutato(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, status=ReceiverStatus.DISABLED)
    redis = await get_redis()
    key = f"ingest:rejected:{receiver_id}"
    # Il contatore esiste da 23 ore: alla scadenza mancano 60 minuti.
    await redis.set(key, 1, ex=3600)

    response = await api_client.post(f"/ingest/{slug}", content="rifiutato")

    assert response.status_code == 404
    assert await redis.get(key) == "2"
    # Un nuovo rifiuto non riapre la finestra: la scadenza resta quella di prima.
    assert await redis.ttl(key) <= 3600


@pytest.mark.e2e
async def test_ultimo_invio_non_arretra_se_il_battito_e_gia_piu_recente(api_client, two_tenants):
    tenant_id, _ = two_tenants
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    piu_recente = datetime.now(UTC) + timedelta(hours=1)
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Receiver)
            .where(Receiver.id == receiver_id)
            .values(last_notification_at=piu_recente)
        )

    response = await api_client.post(f"/ingest/{slug}", content="backup")

    assert response.status_code == 201
    async with tenant_session(tenant_id) as session:
        receiver = await session.get(Receiver, receiver_id)
        assert receiver.last_notification_at == piu_recente
