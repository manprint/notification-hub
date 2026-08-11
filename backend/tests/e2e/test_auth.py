"""E2E per autenticazione (spec 9.2, 10.2)."""

import asyncio
import uuid

import pytest

from app.core.security import hash_password
from app.db.session import tenant_session
from app.db.types import UserRole, UserStatus
from app.models.user import User


async def _create_owner(tenant_id: uuid.UUID, email: str, password: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with tenant_session(tenant_id) as session:
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.OWNER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
    return user_id


@pytest.mark.e2e
async def test_login_e_me(api_client, two_tenants):
    tenant_id, _ = two_tenants
    email = f"owner-{tenant_id.hex[:8]}@test.com"
    await _create_owner(tenant_id, email, "correct-horse-battery")

    login_resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 15 * 60

    me_resp = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["email"] == email
    assert body["role"] == "owner"


@pytest.mark.e2e
async def test_login_password_sbagliata_401(api_client, two_tenants):
    tenant_id, _ = two_tenants
    email = f"owner-{tenant_id.hex[:8]}@test.com"
    await _create_owner(tenant_id, email, "correct-horse-battery")

    response = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert response.status_code == 401


@pytest.mark.e2e
async def test_authorization_assente_ritorna_401_non_422(api_client):
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.e2e
async def test_refresh_ruota_il_token_e_rileva_il_riuso(api_client, two_tenants):
    tenant_id, _ = two_tenants
    email = f"owner-{tenant_id.hex[:8]}@test.com"
    await _create_owner(tenant_id, email, "correct-horse-battery")

    login_resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    token1 = login_resp.json()["refresh_token"]

    refresh_resp = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert refresh_resp.status_code == 200
    token2 = refresh_resp.json()["refresh_token"]
    assert token2 != token1

    # Riuso del token gia ruotato: 401 e revoca dell'intera famiglia.
    reuse_resp = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert reuse_resp.status_code == 401

    # token2 apparteneva alla stessa famiglia di token1: deve essere revocato.
    followup_resp = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": token2})
    assert followup_resp.status_code == 401


@pytest.mark.e2e
async def test_due_refresh_concorrenti_non_emettono_due_token_validi(api_client, two_tenants):
    tenant_id, _ = two_tenants
    email = f"owner-{tenant_id.hex[:8]}@test.com"
    await _create_owner(tenant_id, email, "correct-horse-battery")
    login_resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    token = login_resp.json()["refresh_token"]

    responses = await asyncio.gather(
        api_client.post("/api/v1/auth/refresh", json={"refresh_token": token}),
        api_client.post("/api/v1/auth/refresh", json={"refresh_token": token}),
    )
    assert sorted(response.status_code for response in responses) == [200, 401]

    issued = next(
        response.json()["refresh_token"] for response in responses if response.status_code == 200
    )
    # La seconda richiesta e' un riuso: revoca l'intera famiglia, compreso il
    # token che la prima richiesta aveva appena emesso.
    followup = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": issued})
    assert followup.status_code == 401


@pytest.mark.e2e
async def test_logout_revoca_il_refresh_token(api_client, two_tenants):
    tenant_id, _ = two_tenants
    email = f"owner-{tenant_id.hex[:8]}@test.com"
    await _create_owner(tenant_id, email, "correct-horse-battery")

    login_resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    access_token = login_resp.json()["access_token"]
    refresh_token = login_resp.json()["refresh_token"]

    logout_resp = await api_client.post(
        "/api/v1/auth/logout",
        json={"revoke_all": True},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 204

    refresh_resp = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 401


@pytest.mark.e2e
async def test_ultimo_owner_non_puo_essere_rimosso(api_client, two_tenants):
    tenant_id, _ = two_tenants
    email = f"owner-{tenant_id.hex[:8]}@test.com"
    owner_id = await _create_owner(tenant_id, email, "correct-horse-battery")

    login_resp = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
    )
    access_token = login_resp.json()["access_token"]

    response = await api_client.delete(
        f"/api/v1/users/{owner_id}", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 409


@pytest.mark.e2e
async def test_registrazione_pubblica_disabilitata_di_default(api_client):
    response = await api_client.post(
        "/api/v1/auth/register",
        json={"tenant_name": "ACME", "email": f"{uuid.uuid4().hex}@test.com", "password": "x" * 12},
    )
    assert response.status_code == 403
