"""E2E di regressione per i difetti trovati nella review dell'applicazione.

Ogni test qui sotto fallisce sul codice precedente alla review e passa dopo la
correzione: sono i casi che la suite esistente non copriva.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.crypto import encrypt_secret
from app.db.session import tenant_session
from app.db.types import DeliveryStatus, Severity
from app.models.channel import DeliveryChannel
from app.models.delivery import Delivery
from app.models.notification import Notification
from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _headers(api_client, tenant_id: uuid.UUID, owner_token) -> dict:
    return {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}


async def _create_user(api_client, headers, email: str, role: str, group_ids: list) -> dict:
    resp = await api_client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": PASSWORD,
            "role": role,
            "group_ids": [str(g) for g in group_ids],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _login_headers(api_client, email: str) -> dict:
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_channel(tenant_id: uuid.UUID, name: str = "Slack #ops") -> uuid.UUID:
    channel_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            DeliveryChannel(
                id=channel_id,
                tenant_id=tenant_id,
                name=name,
                type="slack",
                webhook_url=encrypt_secret("https://hooks.slack.com/services/T0/B0/X0"),
                enabled=True,
            )
        )
    return channel_id


async def _create_notification(
    tenant_id: uuid.UUID, receiver_id: uuid.UUID, preview: str = "boom"
) -> uuid.UUID:
    notification_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        session.add(
            Notification(
                id=notification_id,
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                content=preview,
                content_preview=preview,
                content_size=len(preview),
                content_normalized=False,
                storage_backend="inline",
                severity=Severity.ERROR,
                severity_source="receiver_default",
                status="unread",
                received_at=datetime.now(UTC),
                source_ip="203.0.113.5",
            )
        )
    return notification_id


# --- Gruppi visibili solo ai propri membri -------------------------------


@pytest.mark.e2e
async def test_lista_gruppi_filtrata_per_membership(api_client, two_tenants, owner_token):
    """Togliere l'associazione a un gruppo doveva togliere anche il gruppo
    dalla lista: prima GET /groups restituiva tutti i gruppi del tenant."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_a = await create_group(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    group_b = await create_group(tenant_id, f"b-{uuid.uuid4().hex[:6]}")

    email = f"m-{uuid.uuid4().hex[:8]}@test.com"
    user = await _create_user(api_client, headers, email, "member", [group_a])
    member_headers = await _login_headers(api_client, email)

    listed = await api_client.get("/api/v1/groups", headers=member_headers)
    assert listed.status_code == 200
    assert [g["id"] for g in listed.json()] == [str(group_a)]

    # L'owner vede entrambi.
    owner_listed = await api_client.get("/api/v1/groups", headers=headers)
    assert {str(group_a), str(group_b)} <= {g["id"] for g in owner_listed.json()}

    # Rimossa l'associazione, il gruppo sparisce.
    patched = await api_client.patch(
        f"/api/v1/users/{user['id']}", json={"group_ids": []}, headers=headers
    )
    assert patched.status_code == 200
    listed_again = await api_client.get("/api/v1/groups", headers=member_headers)
    assert listed_again.json() == []


@pytest.mark.e2e
async def test_dettaglio_gruppo_non_associato_403(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_a = await create_group(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    group_b = await create_group(tenant_id, f"b-{uuid.uuid4().hex[:6]}")

    email = f"m-{uuid.uuid4().hex[:8]}@test.com"
    await _create_user(api_client, headers, email, "member", [group_a])
    member_headers = await _login_headers(api_client, email)

    assert (
        await api_client.get(f"/api/v1/groups/{group_a}", headers=member_headers)
    ).status_code == 200
    assert (
        await api_client.get(f"/api/v1/groups/{group_b}", headers=member_headers)
    ).status_code == 403


@pytest.mark.e2e
async def test_notifiche_scopate_ai_gruppi_associati(api_client, two_tenants, owner_token):
    """member e viewer leggevano le notifiche di tutti i gruppi del tenant."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_a = await create_group(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    group_b = await create_group(tenant_id, f"b-{uuid.uuid4().hex[:6]}")
    receiver_a = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_a)
    receiver_b = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_b)
    n_a = await _create_notification(tenant_id, receiver_a, "gruppo A")
    n_b = await _create_notification(tenant_id, receiver_b, "gruppo B")

    email = f"m-{uuid.uuid4().hex[:8]}@test.com"
    await _create_user(api_client, headers, email, "member", [group_a])
    member_headers = await _login_headers(api_client, email)

    listed = await api_client.get("/api/v1/notifications", headers=member_headers)
    ids = {n["id"] for n in listed.json()["notifications"]}
    assert str(n_a) in ids
    assert str(n_b) not in ids

    assert (
        await api_client.get(f"/api/v1/notifications/{n_b}", headers=member_headers)
    ).status_code == 403
    assert (
        await api_client.get(f"/api/v1/notifications/{n_a}", headers=member_headers)
    ).status_code == 200


# --- Override per receiver ------------------------------------------------


@pytest.mark.e2e
async def test_override_id_malformato_422_non_500(api_client, two_tenants, owner_token):
    """Il campo "Receiver ID" della UI accetta testo libero: un id non valido
    finiva in uuid.UUID() dentro l'endpoint e usciva come 500."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)

    resp = await api_client.get("/api/v1/receivers/non-un-uuid/channels", headers=headers)
    assert resp.status_code == 422

    resp = await api_client.post(
        "/api/v1/receivers/non-un-uuid/channels",
        json={"channel_id": str(uuid.uuid4()), "mode": "mute"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_override_receiver_o_canale_inesistente_404(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])

    ghost = await api_client.post(
        f"/api/v1/receivers/{uuid.uuid4()}/channels",
        json={"channel_id": str(await _create_channel(tenant_id)), "mode": "mute"},
        headers=headers,
    )
    assert ghost.status_code == 404

    ghost_channel = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/channels",
        json={"channel_id": str(uuid.uuid4()), "mode": "mute"},
        headers=headers,
    )
    assert ghost_channel.status_code == 404


@pytest.mark.e2e
async def test_override_salvato_due_volte_aggiorna(api_client, two_tenants, owner_token):
    """Il secondo salvataggio violava il vincolo di unicita (500): ora e un
    aggiornamento idempotente."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    channel_id = await _create_channel(tenant_id)

    first = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/channels",
        json={"channel_id": str(channel_id), "mode": "override", "min_severity": "error"},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/channels",
        json={"channel_id": str(channel_id), "mode": "mute"},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["mode"] == "mute"
    assert second.json()["min_severity"] is None


@pytest.mark.e2e
async def test_override_senza_soglia_rifiutato(api_client, two_tenants, owner_token):
    """mode=override senza min_severity mandava in assert il worker."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22])
    channel_id = await _create_channel(tenant_id)

    created = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/channels",
        json={"channel_id": str(channel_id), "mode": "mute"},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    promoted = await api_client.put(
        f"/api/v1/receivers/{receiver_id}/channels/{channel_id}",
        json={"mode": "override"},
        headers=headers,
    )
    assert promoted.status_code == 422


# --- Canali ---------------------------------------------------------------


@pytest.mark.e2e
async def test_cancellazione_canale_con_binding_e_consegne(api_client, two_tenants, owner_token):
    """Le FK verso delivery_channels non hanno ON DELETE: cancellare un canale
    in uso usciva come 500."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_id)
    notification_id = await _create_notification(tenant_id, receiver_id)
    channel_id = await _create_channel(tenant_id)

    bound = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": str(channel_id), "min_severity": "error"},
        headers=headers,
    )
    assert bound.status_code == 201, bound.text

    override = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/channels",
        json={"channel_id": str(channel_id), "mode": "mute"},
        headers=headers,
    )
    assert override.status_code == 201, override.text

    async with tenant_session(tenant_id) as session:
        session.add(
            Delivery(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                notification_id=notification_id,
                channel_id=channel_id,
                status=DeliveryStatus.DEAD,
                attempts=5,
                next_attempt_at=datetime.now(UTC),
            )
        )

    deleted = await api_client.delete(f"/api/v1/channels/{channel_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text


@pytest.mark.e2e
async def test_binding_gruppo_canale_idempotente(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    channel_id = await _create_channel(tenant_id)

    first = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": str(channel_id), "min_severity": "error"},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": str(channel_id), "min_severity": "warning"},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["min_severity"] == "warning"
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.e2e
async def test_canale_con_url_non_http_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)

    resp = await api_client.post(
        "/api/v1/channels",
        json={"name": "cattivo", "type": "slack", "webhook_url": "hooks.slack.com/senza-schema"},
        headers=headers,
    )
    assert resp.status_code == 422


# --- Consegne -------------------------------------------------------------


@pytest.mark.e2e
async def test_consegne_riportano_canale_e_receiver(api_client, two_tenants, owner_token):
    """La pagina Consegne mostrava solo stato e contatori: la riga ora dice
    quale notifica e stata inoltrata e verso quale canale."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_id = await create_group(tenant_id, f"g-{uuid.uuid4().hex[:6]}")
    receiver_id = await create_receiver(
        tenant_id, uuid.uuid4().hex[:22], group_id=group_id, name="Backup notturno"
    )
    notification_id = await _create_notification(tenant_id, receiver_id, "disco pieno")
    channel_id = await _create_channel(tenant_id, name="Slack #ops")

    async with tenant_session(tenant_id) as session:
        session.add(
            Delivery(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                notification_id=notification_id,
                channel_id=channel_id,
                status=DeliveryStatus.SENT,
                attempts=1,
                next_attempt_at=datetime.now(UTC),
            )
        )

    listed = await api_client.get("/api/v1/deliveries", headers=headers)
    assert listed.status_code == 200, listed.text
    row = next(d for d in listed.json() if d["notification_id"] == str(notification_id))
    assert row["channel_name"] == "Slack #ops"
    assert row["receiver_name"] == "Backup notturno"
    assert row["content_preview"] == "disco pieno"
    assert row["severity"] == "error"


@pytest.mark.e2e
async def test_consegne_scopate_ai_gruppi_associati(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    group_a = await create_group(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    group_b = await create_group(tenant_id, f"b-{uuid.uuid4().hex[:6]}")
    receiver_b = await create_receiver(tenant_id, uuid.uuid4().hex[:22], group_id=group_b)
    notification_b = await _create_notification(tenant_id, receiver_b)
    channel_id = await _create_channel(tenant_id)

    async with tenant_session(tenant_id) as session:
        session.add(
            Delivery(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                notification_id=notification_b,
                channel_id=channel_id,
                status=DeliveryStatus.SENT,
                attempts=1,
                next_attempt_at=datetime.now(UTC),
            )
        )

    email = f"m-{uuid.uuid4().hex[:8]}@test.com"
    await _create_user(api_client, headers, email, "member", [group_a])
    member_headers = await _login_headers(api_client, email)

    listed = await api_client.get("/api/v1/deliveries", headers=member_headers)
    assert listed.status_code == 200
    assert all(d["notification_id"] != str(notification_b) for d in listed.json())


# --- Utenti ---------------------------------------------------------------


@pytest.mark.e2e
async def test_ruolo_fuori_dominio_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    email = f"m-{uuid.uuid4().hex[:8]}@test.com"
    user = await _create_user(api_client, headers, email, "member", [])

    resp = await api_client.patch(
        f"/api/v1/users/{user['id']}", json={"role": "superuser"}, headers=headers
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_disabilitare_ultimo_owner_409(api_client, two_tenants, owner_token):
    """remove_user proteggeva l'ultimo owner, PATCH status=disabled no."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    me = await api_client.get("/api/v1/auth/me", headers=headers)
    owner_id = me.json()["id"]

    resp = await api_client.patch(
        f"/api/v1/users/{owner_id}", json={"status": "disabled"}, headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["type"] == "/problems/last-owner"


@pytest.mark.e2e
async def test_admin_non_promuove_a_owner(api_client, two_tenants, owner_token):
    """Un admin poteva autopromuoversi owner e superare i vincoli riservati
    al ruolo owner."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)

    admin_email = f"adm-{uuid.uuid4().hex[:8]}@test.com"
    admin = await _create_user(api_client, headers, admin_email, "admin", [])
    admin_headers = await _login_headers(api_client, admin_email)

    escalation = await api_client.patch(
        f"/api/v1/users/{admin['id']}", json={"role": "owner"}, headers=admin_headers
    )
    assert escalation.status_code == 403

    new_owner = await api_client.post(
        "/api/v1/users",
        json={
            "email": f"o-{uuid.uuid4().hex[:8]}@test.com",
            "password": PASSWORD,
            "role": "owner",
            "group_ids": [],
        },
        headers=admin_headers,
    )
    assert new_owner.status_code == 403


@pytest.mark.e2e
async def test_invito_a_email_gia_registrata_409(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, tenant_id, owner_token)
    email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
    await _create_user(api_client, headers, email, "member", [])

    resp = await api_client.post(
        "/api/v1/invitations", json={"email": email, "role": "member"}, headers=headers
    )
    assert resp.status_code == 409
