"""E2E: la preflight di cancellazione (spec 9.3) conta in SQL.

Un gruppo con piu di 32767 notifiche faceva fallire delete-impact con un 500: la
query passava tutti gli id come parametri legati, e il protocollo Postgres ne
accetta al massimo 32767. Qui si crea un gruppo con 33000 notifiche e si
verifica che la risposta sia 200 con i conteggi giusti.
"""

import uuid

import pytest
from sqlalchemy import text

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.models.channel import DeliveryChannel
from tests.conftest_factories import create_group, create_receiver

NOTIFICHE = 33000
DELIVERY = 5


@pytest.mark.e2e
async def test_delete_impact_conta_in_sql_oltre_il_limite_dei_parametri(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_id = await create_group(tenant_id, f"grande-{uuid.uuid4().hex[:8]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name="Slack #ops",
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/T0/B0/X0"),
                enabled=True,
            )
        )
        await session.flush()
        # Inserimento in blocco: una riga per notifica, con il contenuto inline minimo.
        await session.execute(
            text(
                "INSERT INTO notifications (id, tenant_id, receiver_id, storage_backend, "
                "content, content_preview, content_size, content_normalized, severity, "
                "severity_source, status, received_at) "
                "SELECT gen_random_uuid(), CAST(:t AS uuid), CAST(:r AS uuid), "
                "'inline', 'x', 'x', 1, true, 'info', 'explicit', 'unread', now() "
                "FROM generate_series(1, CAST(:n AS integer))"
            ),
            {"t": tenant_id, "r": receiver_id, "n": NOTIFICHE},
        )
        await session.execute(
            text(
                "INSERT INTO deliveries (id, tenant_id, notification_id, channel_id, status, "
                "attempts, next_attempt_at) "
                "SELECT gen_random_uuid(), CAST(:t AS uuid), n.id, CAST(:c AS uuid), "
                "'sent', 1, now() "
                "FROM (SELECT id FROM notifications WHERE receiver_id = CAST(:r AS uuid) "
                "LIMIT CAST(:k AS integer)) n"
            ),
            {"t": tenant_id, "c": channel_id, "r": receiver_id, "k": DELIVERY},
        )

    response = await api_client.get(f"/api/v1/groups/{group_id}/delete-impact", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"receivers": 1, "notifications": NOTIFICHE, "deliveries": DELIVERY}
