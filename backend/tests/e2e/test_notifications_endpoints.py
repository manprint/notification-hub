import uuid

import pytest

from tests.conftest import make_user


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_notifications(api_client, two_tenants):
    """GET /notifications lists user notifications."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        "/api/v1/notifications?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "notifications" in data
    assert "total" in data
    assert "unread_count" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_notifications_filter_status(api_client, two_tenants):
    """GET /notifications filters by status."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        "/api/v1/notifications?status=unread&limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "notifications" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mark_notifications_read(api_client, two_tenants):
    """POST /notifications/mark-read marks notifications as read."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.post(
        "/api/v1/notifications/mark-read",
        json={"notification_ids": [str(uuid.uuid4())]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "marked_read" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_archive_notifications(api_client, two_tenants):
    """POST /notifications/archive archives notifications."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.post(
        "/api/v1/notifications/archive",
        json={"notification_ids": [str(uuid.uuid4())]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "archived" in data
