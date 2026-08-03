"""E2E per l'associazione utente-gruppo e lo scoping dei permessi CRUD sui
receiver: owner/admin CRUD su tutti i gruppi, member CRUD solo sui gruppi
associati, viewer solo lettura sui gruppi associati."""

import uuid

import pytest

from tests.conftest_factories import create_group, create_receiver

PASSWORD = "correct-horse-battery"  # noqa: S105


async def _login(api_client, email: str) -> str:
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _create_user(api_client, owner_headers, email: str, role: str, group_ids: list) -> dict:
    resp = await api_client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": PASSWORD,
            "role": role,
            "group_ids": [str(g) for g in group_ids],
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.e2e
async def test_creazione_utente_con_gruppi(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, f"g-{tenant_id.hex[:6]}")

    body = await _create_user(
        api_client, headers, f"member-{tenant_id.hex[:8]}@test.com", "member", [group_id]
    )
    assert body["group_ids"] == [str(group_id)]

    get_resp = await api_client.get(f"/api/v1/users/{body['id']}", headers=headers)
    assert get_resp.json()["group_ids"] == [str(group_id)]


@pytest.mark.e2e
async def test_creazione_utente_gruppo_sconosciuto_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}

    resp = await api_client.post(
        "/api/v1/users",
        json={
            "email": f"x-{tenant_id.hex[:8]}@test.com",
            "password": PASSWORD,
            "role": "member",
            "group_ids": [str(uuid.uuid4())],
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.e2e
async def test_modifica_utente_sostituisce_gruppi(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_a = await create_group(tenant_id, f"a-{tenant_id.hex[:6]}")
    group_b = await create_group(tenant_id, f"b-{tenant_id.hex[:6]}")

    body = await _create_user(
        api_client, headers, f"member2-{tenant_id.hex[:8]}@test.com", "member", [group_a]
    )

    patch_resp = await api_client.patch(
        f"/api/v1/users/{body['id']}", json={"group_ids": [str(group_b)]}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["group_ids"] == [str(group_b)]


@pytest.mark.e2e
async def test_member_crud_solo_sul_gruppo_associato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner_headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    own_group = await create_group(tenant_id, f"own-{tenant_id.hex[:6]}")
    other_group = await create_group(tenant_id, f"other-{tenant_id.hex[:6]}")

    email = f"member3-{tenant_id.hex[:8]}@test.com"
    await _create_user(api_client, owner_headers, email, "member", [own_group])
    member_headers = {"Authorization": f"Bearer {await _login(api_client, email)}"}

    ok = await api_client.post(
        f"/api/v1/groups/{own_group}/receivers",
        json={"name": "R1"},
        headers=member_headers,
    )
    assert ok.status_code == 201, ok.text

    forbidden = await api_client.post(
        f"/api/v1/groups/{other_group}/receivers",
        json={"name": "R2"},
        headers=member_headers,
    )
    assert forbidden.status_code == 403

    forbidden_list = await api_client.get(
        f"/api/v1/groups/{other_group}/receivers", headers=member_headers
    )
    assert forbidden_list.status_code == 403


@pytest.mark.e2e
async def test_viewer_sola_lettura_sul_gruppo_associato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner_headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, f"view-{tenant_id.hex[:6]}")
    receiver_id = await create_receiver(tenant_id, f"slug-{tenant_id.hex[:8]}", group_id=group_id)

    email = f"viewer-{tenant_id.hex[:8]}@test.com"
    await _create_user(api_client, owner_headers, email, "viewer", [group_id])
    viewer_headers = {"Authorization": f"Bearer {await _login(api_client, email)}"}

    read = await api_client.get(f"/api/v1/receivers/{receiver_id}", headers=viewer_headers)
    assert read.status_code == 200

    write = await api_client.patch(
        f"/api/v1/receivers/{receiver_id}", json={"name": "renamed"}, headers=viewer_headers
    )
    assert write.status_code == 403


@pytest.mark.e2e
async def test_viewer_senza_associazione_403_anche_in_lettura(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner_headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, f"noaccess-{tenant_id.hex[:6]}")
    receiver_id = await create_receiver(tenant_id, f"slug2-{tenant_id.hex[:8]}", group_id=group_id)

    email = f"viewer2-{tenant_id.hex[:8]}@test.com"
    await _create_user(api_client, owner_headers, email, "viewer", [])
    viewer_headers = {"Authorization": f"Bearer {await _login(api_client, email)}"}

    read = await api_client.get(f"/api/v1/receivers/{receiver_id}", headers=viewer_headers)
    assert read.status_code == 403


@pytest.mark.e2e
async def test_owner_e_admin_crud_su_qualunque_gruppo(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    owner_headers = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    group_id = await create_group(tenant_id, f"any-{tenant_id.hex[:6]}")

    email = f"admin-{tenant_id.hex[:8]}@test.com"
    await _create_user(api_client, owner_headers, email, "admin", [])
    admin_headers = {"Authorization": f"Bearer {await _login(api_client, email)}"}

    resp = await api_client.post(
        f"/api/v1/groups/{group_id}/receivers", json={"name": "R"}, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
