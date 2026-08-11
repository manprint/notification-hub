"""E2E per il toggle verified/unread via PATCH (spec 9.5)."""

import uuid

import pytest

from tests.conftest_factories import create_receiver


@pytest.mark.e2e
async def test_patch_verified_persiste(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ingest_resp = await api_client.post(f"/ingest/{slug}", content="da verificare")
    notification_id = ingest_resp.json()["id"]

    patch_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"verified": True}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["verified"] is True
    assert patch_resp.json()["status"] == "unread"

    detail = await api_client.get(f"/api/v1/notifications/{notification_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["verified"] is True
    assert detail.json()["status"] == "unread"


@pytest.mark.e2e
async def test_toggle_status_torna_indietro_e_verified_ignora_unread_count(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ingest_resp = await api_client.post(f"/ingest/{slug}", content="toggle")
    notification_id = ingest_resp.json()["id"]

    list_before = await api_client.get("/api/v1/notifications", headers=headers)
    unread_before = list_before.json()["unread_count"]

    read_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "read"}, headers=headers
    )
    assert read_resp.json()["status"] == "read"

    unread_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "unread"}, headers=headers
    )
    assert unread_resp.status_code == 200
    assert unread_resp.json()["status"] == "unread"

    verified_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"verified": True}, headers=headers
    )
    assert verified_resp.status_code == 200
    assert verified_resp.json()["verified"] is True

    list_after = await api_client.get("/api/v1/notifications", headers=headers)
    assert list_after.json()["unread_count"] == unread_before


@pytest.mark.e2e
async def test_patch_body_vuoto_422(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ingest_resp = await api_client.post(f"/ingest/{slug}", content="vuoto")
    notification_id = ingest_resp.json()["id"]

    patch_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={}, headers=headers
    )
    assert patch_resp.status_code == 422


@pytest.mark.e2e
async def test_lista_e_dettaglio_espongono_verified_default_false(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ingest_resp = await api_client.post(f"/ingest/{slug}", content="default")
    notification_id = ingest_resp.json()["id"]

    list_resp = await api_client.get("/api/v1/notifications", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["notifications"][0]["verified"] is False

    detail = await api_client.get(f"/api/v1/notifications/{notification_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["verified"] is False
