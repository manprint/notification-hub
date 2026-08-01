import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_login_success(api_client, two_tenants, owner_conn):
    """Login with valid credentials."""
    from tests.conftest import make_user

    tenant_a_id, _ = two_tenants
    await make_user(tenant_a_id, "user@test.com")

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_login_invalid_credentials(api_client, two_tenants):
    """Login fails with invalid password."""
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "wrong"},
    )

    assert response.status_code == 401


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_login_rate_limit(api_client, two_tenants):
    """Login rate limited after 5 attempts."""
    for i in range(5):
        response = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "user@test.com", "password": "wrong"},
        )
        if i < 4:
            assert response.status_code == 401

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "wrong"},
    )
    assert response.status_code == 429


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_me_endpoint(api_client, two_tenants):
    """GET /me returns current user."""
    from tests.conftest import make_user

    tenant_a_id, _ = two_tenants
    await make_user(tenant_a_id, "me@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "me@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@test.com"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_refresh_token(api_client, two_tenants):
    """Refresh token endpoint returns new token pair."""
    from tests.conftest import make_user

    tenant_a_id, _ = two_tenants
    await make_user(tenant_a_id, "refresh@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@test.com", "password": "test"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_logout(api_client, two_tenants):
    """Logout endpoint revokes token."""
    from tests.conftest import make_user

    tenant_a_id, _ = two_tenants
    await make_user(tenant_a_id, "logout@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "logout@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]
    jti = login_response.json()["jti"]

    response = await api_client.post(
        "/api/v1/auth/logout",
        json={"jti": jti, "revoke_all": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204

    me_response = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 401
