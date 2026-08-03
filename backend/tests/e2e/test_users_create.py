"""E2E per la creazione diretta di utenze da pannello admin (email + password
specificate dall'owner/admin, senza passare per l'invito via email)."""

import pytest


@pytest.mark.e2e
async def test_creazione_diretta_utente(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    email = f"diretto-{tenant_id.hex[:8]}@test.com"

    response = await api_client.post(
        "/api/v1/users",
        json={"email": email, "password": "correct-horse-battery", "role": "member"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "member"
    assert body["status"] == "active"

    login_resp = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert login_resp.status_code == 200


@pytest.mark.e2e
async def test_creazione_diretta_utente_email_duplicata(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "email": f"duplicato-{tenant_id.hex[:8]}@test.com",
        "password": "correct-horse-battery",
        "role": "member",
    }

    first = await api_client.post("/api/v1/users", json=payload, headers=headers)
    assert first.status_code == 201

    second = await api_client.post("/api/v1/users", json=payload, headers=headers)
    assert second.status_code == 409


@pytest.mark.e2e
async def test_creazione_diretta_utente_richiede_admin(api_client, two_tenants, make_user):
    from app.core.security import hash_password

    tenant_id, _ = two_tenants
    member_email = f"member-{tenant_id.hex[:8]}@test.com"
    await make_user(tenant_id, member_email, hash_password("correct-horse-battery"))

    login_resp = await api_client.post(
        "/api/v1/auth/login",
        json={"email": member_email, "password": "correct-horse-battery"},
    )
    token = login_resp.json()["access_token"]

    response = await api_client.post(
        "/api/v1/users",
        json={
            "email": f"altro-{tenant_id.hex[:8]}@test.com",
            "password": "correct-horse-battery",
            "role": "member",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
