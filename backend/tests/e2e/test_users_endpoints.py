import uuid

import pytest
from sqlalchemy import update

from app.db.session import tenant_session
from app.db.types import UserRole
from app.models.user import User
from tests.conftest import make_user


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_users(api_client, two_tenants):
    """GET /users lists tenant users."""
    tenant_a_id, _ = two_tenants

    admin = await make_user(tenant_a_id, "admin@test.com")
    await make_user(tenant_a_id, "member1@test.com")
    await make_user(tenant_a_id, "member2@test.com")

    async with tenant_session(tenant_a_id) as session:
        await session.execute(update(User).where(User.id == admin.id).values(role=UserRole.ADMIN))
        await session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_user(api_client, two_tenants):
    """GET /users/{id} returns user details."""
    tenant_a_id, _ = two_tenants

    user = await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        f"/api/v1/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@test.com"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_user_not_found(api_client, two_tenants):
    """GET /users/{id} returns 404 for nonexistent user."""
    tenant_a_id, _ = two_tenants

    await make_user(tenant_a_id, "user@test.com")

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.get(
        f"/api/v1/users/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_update_user_role(api_client, two_tenants):
    """PATCH /users/{id} updates user role."""
    tenant_a_id, _ = two_tenants

    admin = await make_user(tenant_a_id, "admin@test.com")
    member = await make_user(tenant_a_id, "member@test.com")

    async with tenant_session(tenant_a_id) as session:
        await session.execute(update(User).where(User.id == admin.id).values(role=UserRole.ADMIN))
        await session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.patch(
        f"/api/v1/users/{member.id}",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_deactivate_user(api_client, two_tenants):
    """POST /users/{id}/deactivate deactivates user."""
    tenant_a_id, _ = two_tenants

    admin = await make_user(tenant_a_id, "admin@test.com")
    user = await make_user(tenant_a_id, "user@test.com")

    async with tenant_session(tenant_a_id) as session:
        await session.execute(update(User).where(User.id == admin.id).values(role=UserRole.ADMIN))
        await session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "test"},
    )
    token = login_response.json()["access_token"]

    response = await api_client.post(
        f"/api/v1/users/{user.id}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
