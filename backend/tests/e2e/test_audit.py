"""E2E dell'audit (spec 9.6): chi ha fatto cosa, con attenzione a "segna come
letta" e "segna come verificata"."""

import uuid

import pytest

from app.core.security import hash_password
from app.db.session import tenant_session
from app.db.types import UserRole, UserStatus
from app.models.user import User
from app.models.user_group_membership import UserGroupMembership
from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _user_with_token(
    api_client, tenant_id: uuid.UUID, role: UserRole
) -> tuple[uuid.UUID, str, str]:
    user_id = uuid.uuid4()
    email = f"{role.value}-{uuid.uuid4().hex[:8]}@test.com"
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=role,
                status=UserStatus.ACTIVE,
            )
        )
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return user_id, email, resp.json()["access_token"]


async def _token_for_role(api_client, tenant_id: uuid.UUID, role: UserRole) -> str:
    _, _, token = await _user_with_token(api_client, tenant_id, role)
    return token


async def _join_group(tenant_id: uuid.UUID, user_id: uuid.UUID, group_id: uuid.UUID) -> None:
    """Un member scrive solo sui gruppi a cui appartiene (services/authz.py)."""
    async with tenant_session(tenant_id) as session:
        session.add(UserGroupMembership(tenant_id=tenant_id, user_id=user_id, group_id=group_id))


async def _ingest(api_client, tenant_id: uuid.UUID, body: str = "contenuto") -> tuple[str, str]:
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    resp = await api_client.post(f"/ingest/{slug}", content=body)
    assert resp.status_code in (201, 202), resp.text
    return slug, resp.json()["id"]


@pytest.mark.e2e
async def test_verifica_di_un_member_finisce_nell_audit_dell_owner(
    api_client, two_tenants, owner_token
):
    """Lo scenario di riferimento del piano: un member verifica, l'owner vede
    chi e' stato, quando, da quale IP e il passaggio false -> true."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    member_id, _, member_token = await _user_with_token(api_client, tenant_id, UserRole.MEMBER)
    member = {"Authorization": f"Bearer {member_token}"}

    group_id = await create_group(tenant_id, f"Gruppo {uuid.uuid4().hex[:6]}")
    await _join_group(tenant_id, member_id, group_id)
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, group_id)
    notification_id = (await api_client.post(f"/ingest/{slug}", content="da verificare")).json()[
        "id"
    ]

    patch = await api_client.patch(
        f"/api/v1/notifications/{notification_id}",
        json={"verified": True},
        headers=member,
    )
    assert patch.status_code == 200

    resp = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"notification_id": notification_id},
        headers=owner,
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert len(events) == 1
    event = events[0]
    assert event["action"] == "notification.marked_verified"
    assert event["actor_role"] == "member"
    assert event["resource_id"] == notification_id
    assert event["outcome"] == "success"
    assert event["changes"]["verified"] == {"before": False, "after": True}
    assert event["ip"] is not None


@pytest.mark.e2e
async def test_lo_storico_conserva_anche_i_ripristini(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    _, notification_id = await _ingest(api_client, tenant_id)

    for verified in (True, False, True):
        resp = await api_client.patch(
            f"/api/v1/notifications/{notification_id}",
            json={"verified": verified},
            headers=owner,
        )
        assert resp.status_code == 200

    resp = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"notification_id": notification_id},
        headers=owner,
    )
    actions = [event["action"] for event in resp.json()["events"]]
    # Ordine decrescente: l'ultimo fatto per primo.
    assert actions == [
        "notification.marked_verified",
        "notification.marked_unverified",
        "notification.marked_verified",
    ]


@pytest.mark.e2e
async def test_una_patch_che_non_cambia_nulla_non_lascia_evento(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    _, notification_id = await _ingest(api_client, tenant_id)

    for _ in range(2):
        resp = await api_client.patch(
            f"/api/v1/notifications/{notification_id}",
            json={"status": "read"},
            headers=owner,
        )
        assert resp.status_code == 200

    resp = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"notification_id": notification_id},
        headers=owner,
    )
    assert [e["action"] for e in resp.json()["events"]] == ["notification.marked_read"]


@pytest.mark.e2e
async def test_lettura_e_verifica_insieme_sono_due_eventi(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    _, notification_id = await _ingest(api_client, tenant_id)

    resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}",
        json={"status": "read", "verified": True},
        headers=owner,
    )
    assert resp.status_code == 200
    # I due campi denormalizzati rispondono "chi ha gestito questa notifica" a
    # chiunque la veda, senza passare dall'audit.
    assert resp.json()["read_by_email"] is not None
    assert resp.json()["verified_by_email"] == resp.json()["read_by_email"]

    resp = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"notification_id": notification_id},
        headers=owner,
    )
    actions = sorted(event["action"] for event in resp.json()["events"])
    assert actions == ["notification.marked_read", "notification.marked_verified"]


@pytest.mark.e2e
async def test_bulk_read_lascia_un_evento_che_ritrova_la_singola_notifica(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    ids = []
    for index in range(3):
        resp = await api_client.post(f"/ingest/{slug}", content=f"bulk {index}")
        ids.append(resp.json()["id"])

    bulk = await api_client.post(
        "/api/v1/notifications/bulk-read",
        json={"receiver_id": str(receiver_id)},
        headers=owner,
    )
    assert bulk.status_code == 200
    assert bulk.json()["marked_read"] == 3

    resp = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"notification_id": ids[1]},
        headers=owner,
    )
    events = resp.json()["events"]
    assert len(events) == 1
    event = events[0]
    assert event["action"] == "notification.bulk_marked_read"
    assert event["context"]["count"] == 3
    assert sorted(event["context"]["notification_ids"]) == sorted(ids)
    assert event["context"]["filters"]["receiver_id"] == str(receiver_id)


@pytest.mark.e2e
async def test_audit_vietato_a_member_e_viewer(api_client, two_tenants):
    tenant_id, _ = two_tenants
    for role in (UserRole.MEMBER, UserRole.VIEWER):
        token = await _token_for_role(api_client, tenant_id, role)
        headers = {"Authorization": f"Bearer {token}"}
        for path in ("/api/v1/audit/events", "/api/v1/audit/notification-status"):
            resp = await api_client.get(path, headers=headers)
            assert resp.status_code == 403, f"{role.value} {path}"
        resp = await api_client.get("/api/v1/audit/export", headers=headers)
        assert resp.status_code == 403


@pytest.mark.e2e
async def test_audit_permesso_ad_admin(api_client, two_tenants):
    tenant_id, _ = two_tenants
    token = await _token_for_role(api_client, tenant_id, UserRole.ADMIN)
    resp = await api_client.get(
        "/api/v1/audit/events", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200


@pytest.mark.e2e
async def test_un_tenant_non_vede_gli_eventi_dell_altro(api_client, two_tenants, owner_token):
    tenant_a, tenant_b = two_tenants
    owner_a = {"Authorization": f"Bearer {await owner_token(api_client, tenant_a)}"}
    owner_b = {"Authorization": f"Bearer {await owner_token(api_client, tenant_b)}"}
    _, notification_id = await _ingest(api_client, tenant_a)
    await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"verified": True}, headers=owner_a
    )

    resp = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"notification_id": notification_id},
        headers=owner_b,
    )
    assert resp.status_code == 200
    assert resp.json()["events"] == []


@pytest.mark.e2e
async def test_login_fallito_di_un_utente_esistente_e_registrato(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    email = f"member-{uuid.uuid4().hex[:8]}@test.com"
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=UserRole.MEMBER,
                status=UserStatus.ACTIVE,
            )
        )

    resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "sbagliata"}
    )
    assert resp.status_code == 401

    audit = await api_client.get(
        "/api/v1/audit/events",
        params={"action": "auth.login_failed", "outcome": "failure"},
        headers=owner,
    )
    events = [e for e in audit.json()["events"] if e["actor_email"] == email]
    assert len(events) == 1
    assert events[0]["context"]["reason"] == "invalid_password"


@pytest.mark.e2e
async def test_login_riuscito_e_logout_sono_registrati(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    audit = await api_client.get(
        "/api/v1/audit/events", params={"action": "auth.login"}, headers=owner
    )
    assert audit.status_code == 200
    assert len(audit.json()["events"]) >= 1


@pytest.mark.e2e
async def test_ingestion_non_produce_eventi(api_client, two_tenants, owner_token):
    """L'ingestion non ha attore umano: la notifica e' gia il proprio registro."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    _, notification_id = await _ingest(api_client, tenant_id)

    resp = await api_client.get(
        "/api/v1/audit/events",
        params={"resource_type": "notification", "resource_id": notification_id},
        headers=owner,
    )
    assert resp.json()["events"] == []


@pytest.mark.e2e
async def test_modifica_di_un_receiver_e_tracciata_senza_codice_nel_router(
    api_client, two_tenants, owner_token
):
    """L'hook before_flush copre ogni mutazione passata dall'ORM: nessuno deve
    ricordarsi di scrivere l'audit endpoint per endpoint."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)

    resp = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"name": "Nome nuovo"}, headers=owner
    )
    assert resp.status_code == 200

    audit = await api_client.get(
        "/api/v1/audit/events",
        params={"resource_type": "receiver", "resource_id": str(receiver_id)},
        headers=owner,
    )
    events = audit.json()["events"]
    assert [e["action"] for e in events] == ["receiver.updated"]
    assert events[0]["changes"]["name"]["after"] == "Nome nuovo"


@pytest.mark.e2e
async def test_i_segreti_dei_canali_non_finiscono_nell_audit(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    created = await api_client.post(
        "/api/v1/channels",
        json={
            "name": f"Slack {uuid.uuid4().hex[:6]}",
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/T000/B000/XXXsegretoXXX",
            "enabled": True,
        },
        headers=owner,
    )
    assert created.status_code == 201, created.text

    audit = await api_client.get(
        "/api/v1/audit/events",
        params={"resource_type": "delivery_channel", "resource_id": created.json()["id"]},
        headers=owner,
    )
    event = audit.json()["events"][0]
    assert event["action"] == "delivery_channel.created"
    assert event["changes"]["webhook_url"]["after"] == "[redacted]"
    assert "XXXsegretoXXX" not in audit.text


@pytest.mark.e2e
async def test_export_csv_restituisce_un_allegato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    _, notification_id = await _ingest(api_client, tenant_id)
    await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "read"}, headers=owner
    )

    resp = await api_client.get(
        "/api/v1/audit/export",
        params={"notification_status_only": True, "format": "csv"},
        headers=owner,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "notification.marked_read" in resp.text


@pytest.mark.e2e
async def test_export_json_rispetta_i_filtri(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    resp = await api_client.get(
        "/api/v1/audit/export",
        params={"format": "json", "action": "auth.login"},
        headers=owner,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload
    assert {event["action"] for event in payload} == {"auth.login"}


@pytest.mark.e2e
async def test_paginazione_a_cursore(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)
    for index in range(3):
        resp = await api_client.post(f"/ingest/{slug}", content=f"pagina {index}")
        await api_client.patch(
            f"/api/v1/notifications/{resp.json()['id']}",
            json={"verified": True},
            headers=owner,
        )

    first = await api_client.get(
        "/api/v1/audit/notification-status", params={"limit": 2}, headers=owner
    )
    assert len(first.json()["events"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor is not None

    second = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"limit": 2, "cursor": cursor},
        headers=owner,
    )
    first_ids = {event["id"] for event in first.json()["events"]}
    second_ids = {event["id"] for event in second.json()["events"]}
    assert not (first_ids & second_ids)


@pytest.mark.e2e
async def test_cursore_non_valido_e_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    resp = await api_client.get(
        "/api/v1/audit/events", params={"cursor": "non-un-cursore"}, headers=owner
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_l_evento_di_un_receiver_dice_in_quale_gruppo_sta(
    api_client, two_tenants, owner_token
):
    """Senza il gruppo, "receiver / Backup notturno" non identifica niente: lo
    stesso nome puo' stare in tre gruppi diversi."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")
    receiver_id = await create_receiver(
        tenant_id, uuid.uuid4().hex[:22], group_id=group_id, name="Backup notturno"
    )

    resp = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"name": "Backup notturno"}, headers=owner
    )
    assert resp.status_code == 200
    await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"rate_limit_per_min": 30}, headers=owner
    )

    audit = await api_client.get(
        "/api/v1/audit/events",
        params={"resource_type": "receiver", "resource_id": str(receiver_id)},
        headers=owner,
    )
    evento = audit.json()["events"][0]
    assert evento["group_name"] == "Server Produzione"
    assert evento["receiver_name"] == "Backup notturno"
    # Gli id ci sono: l'interfaccia ci mette sopra il collegamento.
    assert evento["receiver_id"] == str(receiver_id)
    assert evento["group_id"] == str(group_id)


@pytest.mark.e2e
async def test_anche_una_regola_di_severity_dice_su_quale_receiver_sta(
    api_client, two_tenants, owner_token
):
    """Una regola si racconta con il suo pattern: senza il receiver non si sa
    dove e' stata aggiunta."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")
    receiver_id = await create_receiver(
        tenant_id, uuid.uuid4().hex[:22], group_id=group_id, name="Backup notturno"
    )

    resp = await api_client.post(
        f"/api/v1/receivers/{receiver_id}/severity-rules",
        json={"pattern": "disco pieno", "severity": "critical", "priority": 1},
        headers=owner,
    )
    assert resp.status_code == 201, resp.text

    audit = await api_client.get(
        "/api/v1/audit/events", params={"resource_type": "severity_rule"}, headers=owner
    )
    evento = audit.json()["events"][0]
    assert evento["resource_label"] == "disco pieno"
    assert evento["receiver_name"] == "Backup notturno"
    assert evento["group_name"] == "Server Produzione"


@pytest.mark.e2e
async def test_lettura_di_una_notifica_dice_da_quale_receiver_arriva(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, group_id=group_id, name="Backup notturno")
    ingest = await api_client.post(f"/ingest/{slug}", content="disco pieno")
    notification_id = ingest.json()["id"]

    resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "read"}, headers=owner
    )
    assert resp.status_code == 200

    audit = await api_client.get("/api/v1/audit/notification-status", headers=owner)
    evento = audit.json()["events"][0]
    assert evento["receiver_name"] == "Backup notturno"
    assert evento["group_name"] == "Server Produzione"


@pytest.mark.e2e
async def test_il_bulk_read_dice_su_quale_ambito_ha_agito(api_client, two_tenants, owner_token):
    """Il bulk-read non ha una risorsa singola: l'ambito sta nei filtri con cui
    e' stato lanciato, ed e' cio' che serve sapere."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug, group_id=group_id, name="Backup notturno")
    await api_client.post(f"/ingest/{slug}", content="prima")
    await api_client.post(f"/ingest/{slug}", content="seconda")

    resp = await api_client.post(
        "/api/v1/notifications/bulk-read", json={"receiver_id": str(receiver_id)}, headers=owner
    )
    assert resp.status_code == 200, resp.text

    audit = await api_client.get(
        "/api/v1/audit/notification-status",
        params={"action": "notification.bulk_marked_read"},
        headers=owner,
    )
    evento = audit.json()["events"][0]
    assert evento["receiver_name"] == "Backup notturno"
    assert evento["group_name"] == "Server Produzione"


@pytest.mark.e2e
async def test_la_posizione_resta_vuota_se_la_risorsa_e_stata_cancellata(
    api_client, two_tenants, owner_token
):
    """La riga di audit sopravvive alla risorsa: la posizione si risolve in
    lettura, quindi sparisce con essa invece di mentire."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    receiver_id = await create_receiver(tenant_id, uuid.uuid4().hex[:22], name="Effimero")
    await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"rate_limit_per_min": 30}, headers=owner
    )
    assert (
        await api_client.delete(f"/api/v1/receivers/{receiver_id}", headers=owner)
    ).status_code == 204

    audit = await api_client.get(
        "/api/v1/audit/events",
        params={"resource_type": "receiver", "resource_id": str(receiver_id)},
        headers=owner,
    )
    eventi = audit.json()["events"]
    assert eventi, "gli eventi del receiver cancellato restano"
    assert all(e["group_name"] is None and e["receiver_name"] is None for e in eventi)
    # Il nome congelato nell'evento resta: e' l'unica cosa che sopravvive.
    assert eventi[0]["resource_label"] == "Effimero"


@pytest.mark.e2e
async def test_export_csv_porta_gruppo_e_receiver(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")
    receiver_id = await create_receiver(
        tenant_id, uuid.uuid4().hex[:22], group_id=group_id, name="Backup notturno"
    )
    await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"rate_limit_per_min": 30}, headers=owner
    )

    resp = await api_client.get(
        "/api/v1/audit/export",
        params={"format": "csv", "resource_type": "receiver"},
        headers=owner,
    )
    assert resp.status_code == 200
    righe = resp.text.splitlines()
    assert "group_name" in righe[0] and "receiver_name" in righe[0]
    assert any("Server Produzione" in riga and "Backup notturno" in riga for riga in righe[1:])


@pytest.mark.e2e
async def test_l_evento_di_un_gruppo_porta_il_solo_gruppo(api_client, two_tenants, owner_token):
    """Un gruppo non sta dentro un receiver: la colonna porta il gruppo e basta,
    non un receiver inventato."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")

    resp = await api_client.patch(
        f"/api/v1/groups/{group_id}", json={"description": "i server che contano"}, headers=owner
    )
    assert resp.status_code == 200, resp.text

    audit = await api_client.get(
        "/api/v1/audit/events",
        params={"resource_type": "group", "resource_id": str(group_id)},
        headers=owner,
    )
    evento = audit.json()["events"][0]
    assert evento["group_name"] == "Server Produzione"
    assert evento["group_id"] == str(group_id)
    assert evento["receiver_name"] is None
    assert evento["receiver_id"] is None


@pytest.mark.e2e
async def test_il_legame_gruppo_canale_dice_di_quale_gruppo_parla(
    api_client, two_tenants, owner_token
):
    """Un legame gruppo-canale si racconta con due uuid: senza il nome del
    gruppo la riga e' illeggibile."""
    tenant_id, _ = two_tenants
    owner = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, "Server Produzione")
    canale = await api_client.post(
        "/api/v1/channels",
        json={
            "name": f"Slack {uuid.uuid4().hex[:6]}",
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/T000/B000/XXX",
            "enabled": True,
        },
        headers=owner,
    )
    assert canale.status_code == 201, canale.text

    legame = await api_client.post(
        f"/api/v1/groups/{group_id}/channels",
        json={"channel_id": canale.json()["id"], "min_severity": "error", "enabled": True},
        headers=owner,
    )
    assert legame.status_code == 201, legame.text

    audit = await api_client.get(
        "/api/v1/audit/events", params={"resource_type": "group_channel_binding"}, headers=owner
    )
    evento = audit.json()["events"][0]
    assert evento["group_name"] == "Server Produzione"
    assert evento["receiver_name"] is None
