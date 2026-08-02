"""E2E per l'API di consultazione (spec 9.5)."""

import uuid

import pytest

from app.db.session import tenant_session
from app.db.types import Severity
from tests.conftest_factories import create_receiver, create_severity_rule


@pytest.mark.e2e
async def test_lista_esclude_content_completo_e_usa_cursore(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    for i in range(3):
        await api_client.post(f"/ingest/{slug}", content=f"messaggio {i}")

    page1 = await api_client.get("/api/v1/notifications", params={"limit": 2}, headers=headers)
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["notifications"]) == 2
    assert body1["next_cursor"] is not None
    assert "content" not in body1["notifications"][0]

    page2 = await api_client.get(
        "/api/v1/notifications",
        params={"limit": 2, "cursor": body1["next_cursor"]},
        headers=headers,
    )
    assert page2.status_code == 200
    body2 = page2.json()
    ids_page1 = {n["id"] for n in body1["notifications"]}
    ids_page2 = {n["id"] for n in body2["notifications"]}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.e2e
async def test_filtro_severity_min(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    receiver_id = await create_receiver(tenant_id, slug)
    await create_severity_rule(tenant_id, receiver_id, pattern="FALLITO", severity=Severity.ERROR)

    await api_client.post(f"/ingest/{slug}", content="tutto ok")
    await api_client.post(f"/ingest/{slug}", content="Backup FALLITO")

    response = await api_client.get(
        "/api/v1/notifications", params={"severity_min": "error"}, headers=headers
    )
    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["severity"] == "error"


@pytest.mark.e2e
async def test_filtro_full_text_su_content_preview(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    await api_client.post(f"/ingest/{slug}", content="disco pieno su var")
    await api_client.post(f"/ingest/{slug}", content="tutto regolare")

    response = await api_client.get("/api/v1/notifications", params={"q": "disco"}, headers=headers)
    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert len(notifications) == 1
    assert "disco" in notifications[0]["content_preview"]


@pytest.mark.e2e
async def test_download_content_inline(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    ingest_resp = await api_client.post(f"/ingest/{slug}", content="corpo completo")
    notification_id = ingest_resp.json()["id"]

    response = await api_client.get(
        f"/api/v1/notifications/{notification_id}/content", headers=headers
    )
    assert response.status_code == 200
    assert response.text == "corpo completo"


@pytest.mark.e2e
async def test_download_content_object_storage_byte_identico(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=20_971_520)

    large_body = "y" * (1_048_576 + 1)
    ingest_resp = await api_client.post(f"/ingest/{slug}", content=large_body)
    assert ingest_resp.json()["storage_backend"] == "object"
    notification_id = ingest_resp.json()["id"]

    response = await api_client.get(
        f"/api/v1/notifications/{notification_id}/content", headers=headers
    )
    assert response.status_code == 200
    assert response.text == large_body


@pytest.mark.e2e
async def test_patch_segna_letta_e_bulk_read(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    r1 = await api_client.post(f"/ingest/{slug}", content="uno")
    await api_client.post(f"/ingest/{slug}", content="due")
    notification_id = r1.json()["id"]

    patch_resp = await api_client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "read"}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "read"

    bulk_resp = await api_client.post("/api/v1/notifications/bulk-read", json={}, headers=headers)
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["marked_read"] == 1  # solo quella rimasta unread


@pytest.mark.e2e
async def test_delete_notification_accoda_storage_key_per_oggetti(
    api_client, two_tenants, owner_token
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug, max_body_bytes=20_971_520)

    large_body = "z" * (1_048_576 + 1)
    ingest_resp = await api_client.post(f"/ingest/{slug}", content=large_body)
    notification_id = ingest_resp.json()["id"]

    from sqlalchemy import select

    from app.models.notification import Notification

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Notification).where(Notification.id == uuid.UUID(notification_id))
        )
        storage_key = result.scalar_one().storage_key

    delete_resp = await api_client.delete(
        f"/api/v1/notifications/{notification_id}", headers=headers
    )
    assert delete_resp.status_code == 204

    from app.models.object_deletion import PendingObjectDeletion

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(PendingObjectDeletion).where(PendingObjectDeletion.storage_key == storage_key)
        )
        assert result.scalar_one_or_none() is not None


@pytest.mark.e2e
async def test_stats_summary(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    slug = uuid.uuid4().hex[:22]
    await create_receiver(tenant_id, slug)

    await api_client.post(f"/ingest/{slug}", content="uno")
    await api_client.post(f"/ingest/{slug}", content="due")

    response = await api_client.get("/api/v1/stats/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_unread"] >= 2
    assert "info" in body["by_severity"]
    assert body["notifications_last_24h"] >= 2
    assert body["deliveries_dead"] >= 0
    group_row = next(g for g in body["by_group"] if g["unread_count"] >= 2)
    assert group_row["total"] >= 2
