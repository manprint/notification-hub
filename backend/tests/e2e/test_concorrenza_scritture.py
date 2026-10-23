"""E2E: scritture concorrenti sulla stessa riga o sulla stessa coppia.

Le gare si riproducono in modo deterministico: una transazione concorrente tiene
uncommitted la riga contesa, la richiesta sotto test parte in un task e si aspetta
che resti bloccata su un lock (pg_locks), poi la transazione concorrente fa commit.
Senza le correzioni la richiesta esce con un 409 generico, oppure accoda due volte.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.db.session import engine_app
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from tests.conftest_factories import create_group, create_receiver

# 750 * 0.02s = 15s: sotto carico di suite completa la richiesta puo arrivare al lock
# dopo i 4s della prima stima; il ciclo esce appena il lock compare, quindi non rallenta.
ATTESA_MAX_ITERAZIONI = 750


@pytest.fixture(autouse=True)
async def _pool_di_engine_app_pulito():
    # Il pool e' globale e sopravvive ai singoli event loop dei test: una connessione
    # rimasta da un test precedente puo restare appesa senza mai arrivare al lock.
    # Si scarta il pool, cosi ogni gara parte da connessioni nuove nel suo loop.
    await engine_app.dispose()
    yield


async def _attendi_richiesta_bloccata(richiesta: asyncio.Task) -> None:
    """Aspetta che una richiesta concorrente resti in attesa su un lock non concesso."""
    async with engine_app.connect() as osservatore:
        for _ in range(ATTESA_MAX_ITERAZIONI):
            if richiesta.done():
                # Terminata senza mai bloccarsi: il messaggio dice con che esito.
                raise AssertionError(
                    f"la richiesta e' terminata senza bloccarsi: {richiesta.exception()!r}"
                    if richiesta.exception()
                    else f"la richiesta e' terminata senza bloccarsi: {richiesta.result().text}"
                )
            # Una sessione in attesa di lock nel database di questa suite (pg_locks non
            # distingue il database per i lock di transazione, e vede anche le altre suite).
            bloccate = await osservatore.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity"
                    " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            if bloccate:
                return
            await asyncio.sleep(0.02)
    raise AssertionError("la richiesta concorrente non si e' mai bloccata sul lock")


async def _channel(api_client, headers) -> str:
    resp = await api_client.post(
        "/api/v1/channels",
        json={
            "name": f"Slack {uuid.uuid4().hex[:6]}",
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/T0/B0/X0",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _headers(api_client, tenant_id, owner_token) -> dict:
    return {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}


async def _altra_transazione(tenant_id, sql: str, parametri: dict):
    """Apre una transazione concorrente nel tenant, la lascia uncommitted e la restituisce."""
    conn = await engine_app.connect()
    await conn.execute(text(f"SET LOCAL app.tenant_id = '{uuid.UUID(str(tenant_id))}'"))
    await conn.execute(text(sql), parametri)
    return conn


@pytest.mark.e2e
async def test_bind_concorrente_aggiorna_la_riga_gia_inserita(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    channel_id = await _channel(api_client, headers)

    altra = await _altra_transazione(
        tenant_id,
        "INSERT INTO group_channel_bindings"
        " (tenant_id, group_id, channel_id, min_severity, enabled)"
        " VALUES (:t, :g, :c, 'info', true)",
        {"t": tenant_id, "g": group_id, "c": uuid.UUID(channel_id)},
    )
    try:
        richiesta = asyncio.create_task(
            api_client.post(
                f"/api/v1/groups/{group_id}/channels",
                json={"channel_id": channel_id, "min_severity": "error"},
                headers=headers,
            )
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()

    assert resp.status_code == 201, resp.text
    assert resp.json()["min_severity"] == "error"
    elenco = await api_client.get(f"/api/v1/groups/{group_id}/channels", headers=headers)
    assert len(elenco.json()) == 1


@pytest.mark.e2e
async def test_override_concorrente_aggiorna_la_riga_gia_inserita(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    channel_id = await _channel(api_client, headers)

    altra = await _altra_transazione(
        tenant_id,
        "INSERT INTO receiver_channel_overrides (tenant_id, receiver_id, channel_id, mode)"
        " VALUES (:t, :r, :c, 'mute')",
        {"t": tenant_id, "r": receiver_id, "c": uuid.UUID(channel_id)},
    )
    try:
        richiesta = asyncio.create_task(
            api_client.post(
                f"/api/v1/receivers/{receiver_id}/channels",
                json={"channel_id": channel_id, "mode": "override", "min_severity": "critical"},
                headers=headers,
            )
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()

    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "override"


@pytest.mark.e2e
async def test_bind_su_canale_cancellato_nel_frattempo_e_409_non_500(
    api_client, two_tenants, owner_token
):
    """Il canale esiste alla lettura iniziale, poi un'altra transazione lo cancella prima
    dell'inserimento: la violazione di FK non ha una riga da aggiornare, quindi e' un 409."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    channel_id = await _channel(api_client, headers)

    altra = await _altra_transazione(
        tenant_id,
        "DELETE FROM delivery_channels WHERE id = :c",
        {"c": uuid.UUID(channel_id)},
    )
    try:
        richiesta = asyncio.create_task(
            api_client.post(
                f"/api/v1/groups/{group_id}/channels",
                json={"channel_id": channel_id, "min_severity": "error"},
                headers=headers,
            )
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()

    assert resp.status_code == 409, resp.text


@pytest.mark.e2e
async def test_override_su_canale_cancellato_nel_frattempo_e_409_non_500(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    channel_id = await _channel(api_client, headers)

    altra = await _altra_transazione(
        tenant_id,
        "DELETE FROM delivery_channels WHERE id = :c",
        {"c": uuid.UUID(channel_id)},
    )
    try:
        richiesta = asyncio.create_task(
            api_client.post(
                f"/api/v1/receivers/{receiver_id}/channels",
                json={"channel_id": channel_id, "mode": "override", "min_severity": "critical"},
                headers=headers,
            )
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()

    assert resp.status_code == 409, resp.text


@pytest.mark.e2e
async def test_regola_a_priorita_automatica_concorrente_viene_accodata(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)

    # L'altra richiesta ha gia preso la priorita 10, non ancora committata.
    altra = await _altra_transazione(
        tenant_id,
        "INSERT INTO severity_rules (tenant_id, receiver_id, priority, pattern,"
        " case_insensitive, severity, enabled) VALUES (:t, :r, 10, 'altra', true, 'info', true)",
        {"t": tenant_id, "r": receiver_id},
    )
    try:
        richiesta = asyncio.create_task(
            api_client.post(
                f"/api/v1/receivers/{receiver_id}/severity-rules",
                json={"pattern": "mia", "severity": "error"},
                headers=headers,
            )
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()

    assert resp.status_code == 201, resp.text
    assert resp.json()["priority"] == 20


@pytest.mark.e2e
async def test_regola_di_preset_a_priorita_automatica_concorrente_viene_accodata(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    creato = await api_client.post(
        "/api/v1/severity-presets",
        json={"name": f"preset-{uuid.uuid4().hex[:6]}", "description": "test"},
        headers=headers,
    )
    assert creato.status_code == 201, creato.text
    preset_id = creato.json()["id"]

    altra = await _altra_transazione(
        tenant_id,
        "INSERT INTO severity_preset_rules (tenant_id, preset_id, priority, pattern,"
        " case_insensitive, severity, enabled) VALUES (:t, :p, 10, 'altra', true, 'info', true)",
        {"t": tenant_id, "p": uuid.UUID(preset_id)},
    )
    try:
        richiesta = asyncio.create_task(
            api_client.post(
                f"/api/v1/severity-presets/{preset_id}/rules",
                json={"pattern": "mia", "severity": "error"},
                headers=headers,
            )
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()

    assert resp.status_code == 201, resp.text
    assert resp.json()["priority"] == 20


@pytest.mark.e2e
async def test_retry_concorrente_di_una_delivery_dead_non_accoda_due_volte(
    api_client, two_tenants, owner_token
):
    """Il primo retry e' ancora in corso (uncommitted, stato pending) quando arriva il
    secondo: deve vedere lo stato aggiornato e rispondere 409, senza accodare."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"gruppo-{uuid.uuid4().hex[:8]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    channel_id = await _channel(api_client, headers)

    delivery_id = uuid.uuid4()
    async with engine_app.begin() as conn:
        await conn.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
        notification_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO notifications (id, tenant_id, receiver_id, storage_backend, content,"
                " content_preview, content_size, content_normalized, severity, severity_source,"
                " status, received_at) VALUES (:n, :t, :r, 'inline', 'x', 'x', 1, true, 'info',"
                " 'explicit', 'unread', now())"
            ),
            {"n": notification_id, "t": tenant_id, "r": receiver_id},
        )
        await conn.execute(
            text(
                "INSERT INTO deliveries (id, tenant_id, notification_id, channel_id, status,"
                " attempts, next_attempt_at) VALUES (:d, :t, :n, :c, 'dead', 5, now())"
            ),
            {"d": delivery_id, "t": tenant_id, "n": notification_id, "c": uuid.UUID(channel_id)},
        )

    altra = await _altra_transazione(
        tenant_id,
        "UPDATE deliveries SET status = 'pending' WHERE id = :d",
        {"d": delivery_id},
    )
    accodate: list[tuple[str, str]] = []
    set_enqueue_function(lambda delivery, tid: accodate.append((delivery, tid)))
    try:
        richiesta = asyncio.create_task(
            api_client.post(f"/api/v1/deliveries/{delivery_id}/retry", headers=headers)
        )
        await _attendi_richiesta_bloccata(richiesta)
        await altra.commit()
        resp = await richiesta
    finally:
        await altra.close()
        reset_enqueue_function()

    assert resp.status_code == 409, resp.text
    assert accodate == []
