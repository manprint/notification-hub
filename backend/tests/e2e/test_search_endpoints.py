import pytest

from tests.conftest import make_user


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_search_notifications(api_client, two_tenants):
    """POST /search/notifications searches notifications."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.post(
        "/api/v1/search/notifications",
        json={
            "query": "error",
            "skip": 0,
            "limit": 20,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "total" in data
    assert "took_ms" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_search_notifications_with_filters(api_client, two_tenants):
    """POST /search/notifications with severity and status filters."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.post(
        "/api/v1/search/notifications",
        json={
            "severity": ["error", "critical"],
            "status": "unread",
            "skip": 0,
            "limit": 20,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_aggregate_notifications(api_client, two_tenants):
    """GET /search/notifications/aggregate returns aggregations."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        "/api/v1/search/notifications/aggregate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "severity" in data
    assert "status" in data
    assert isinstance(data["severity"], dict)
    assert isinstance(data["status"], dict)
