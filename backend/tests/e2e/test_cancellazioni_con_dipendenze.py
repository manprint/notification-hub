"""E2E: cancellare un gruppo o un receiver che ha binding o override (spec 9.3).

Prima della migrazione 0017 la DELETE rispondeva 204 e la cancellazione falliva
al commit, dopo la risposta: il gruppo restava lì e nessun errore arrivava al
client. Ora il cascade pulisce le dipendenze, e un vincolo che davvero non
regge esce come 409 dentro la richiesta.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.session import tenant_session
from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.delivery import Delivery
from app.models.notification import Notification
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from tests.conftest_factories import create_group, create_receiver


async def _setup_dipendenze(api_client, tenant_id, headers, group_id, receiver_id):
    """Crea un canale, lo lega al gruppo, fa un override sul receiver e ingerisce
    una notifica, cosi che esistano anche notifiche e delivery da cascadare."""
    channel = await api_client.post(
        "/api/v1/channels",
        json={
            "name": f"Slack {uuid.uuid4().hex[:6]}",
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/T0/B0/X0",
        },
        headers=headers,
    )
    assert channel.status_code == 201, channel.text
    channel_id = channel.json()["id"]

    binding = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": channel_id, "min_severity": "info"},
        headers=headers,
    )
    assert binding.status_code == 201, binding.text

    override = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/channels",
        json={"channel_id": channel_id, "mode": "override", "min_severity": "info"},
        headers=headers,
    )
    assert override.status_code == 201, override.text
    return channel_id


async def _conta(tenant_id, model, **filtri) -> int:
    condizioni = [getattr(model, colonna) == valore for colonna, valore in filtri.items()]
    async with tenant_session(tenant_id) as session:
        result = await session.execute(select(func.count()).select_from(model).where(*condizioni))
        return result.scalar_one()


async def _ingest(api_client, slug: str) -> None:
    # Niente Celery nei test: l'enqueue dopo il commit e' un no-op.
    set_enqueue_function(lambda delivery_id, tid: None)
    try:
        resp = await api_client.post(f"/ingest/{slug}", content="backup completato")
        assert resp.status_code == 201, resp.text
    finally:
        reset_enqueue_function()


@pytest.mark.e2e
async def test_delete_gruppo_cascade_su_binding_override_notifiche_e_delivery(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    name = f"gruppo-{uuid.uuid4().hex[:8]}"
    group_id = await create_group(tenant_id, name)
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, group_id=group_id)
    await _setup_dipendenze(api_client, tenant_id, headers, group_id, receiver_id)
    await _ingest(api_client, slug)

    assert await _conta(tenant_id, Notification, receiver_id=receiver_id) == 1
    assert await _conta(tenant_id, Delivery) == 1

    resp = await api_client.delete(f"/api/v1/groups/{group_id}?confirm={name}", headers=headers)
    assert resp.status_code == 204, resp.text

    assert (await api_client.get(f"/api/v1/groups/{group_id}", headers=headers)).status_code == 404
    assert await _conta(tenant_id, GroupChannelBinding, group_id=group_id) == 0
    assert await _conta(tenant_id, ReceiverChannelOverride, receiver_id=receiver_id) == 0
    assert await _conta(tenant_id, Notification, receiver_id=receiver_id) == 0


@pytest.mark.e2e
async def test_delete_receiver_con_override_cancella_davvero(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    await _setup_dipendenze(api_client, tenant_id, headers, group_id, receiver_id)

    resp = await api_client.delete(f"/api/v1/receivers/{receiver_id}", headers=headers)
    assert resp.status_code == 204, resp.text

    assert (
        await api_client.get(f"/api/v1/receivers/{receiver_id}", headers=headers)
    ).status_code == 404
    assert await _conta(tenant_id, ReceiverChannelOverride, receiver_id=receiver_id) == 0
    # Il gruppo e il suo binding restano: si cancella solo il receiver.
    assert await _conta(tenant_id, GroupChannelBinding, group_id=group_id) == 1


@pytest.mark.e2e
async def test_delete_gruppo_non_risponde_204_se_un_vincolo_fallisce(
    api_client, two_tenants, owner_token
):
    """Un vincolo che il cascade non copre deve uscire come errore dentro la
    richiesta, mai come 204 seguito da una cancellazione che non avviene.

    Il vincolo di prova e' una tabella scratch con una FK NO ACTION verso groups,
    creata e rimossa dal ruolo owner (quello delle migrazioni).
    """
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    name = f"gruppo-{uuid.uuid4().hex[:8]}"
    group_id = await create_group(tenant_id, name)

    owner_engine = create_async_engine(get_settings().database_url_owner)
    try:
        async with owner_engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE tmp_blocco_delete_gruppo ("
                    " id uuid PRIMARY KEY,"
                    " group_id uuid NOT NULL REFERENCES groups(id))"
                )
            )
            await conn.execute(
                text("INSERT INTO tmp_blocco_delete_gruppo (id, group_id) VALUES (:i, :g)"),
                {"i": uuid.uuid4(), "g": group_id},
            )
        resp = await api_client.delete(f"/api/v1/groups/{group_id}?confirm={name}", headers=headers)
        assert resp.status_code == 409, resp.text
        assert (
            await api_client.get(f"/api/v1/groups/{group_id}", headers=headers)
        ).status_code == 200
    finally:
        async with owner_engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS tmp_blocco_delete_gruppo"))
        await owner_engine.dispose()
