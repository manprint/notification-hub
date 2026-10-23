"""Revoca dei refresh token e ordine dei lock (spec 4.1, 9.2).

Disabilitare un utente con PATCH deve chiudere le sue sessioni come fa DELETE;
il logout deve chiudere anche le rotazioni concorrenti; refresh e rimozione non
devono formare un ciclo di lock. I test di concorrenza tengono una transazione
aperta a mano: il risultato non dipende dal tempo di esecuzione.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password, hash_token, new_refresh_token
from app.db.session import tenant_session
from app.db.types import UserRole, UserStatus
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "correct-horse-battery"


async def _utente(tenant_id: uuid.UUID, ruolo: UserRole) -> tuple[uuid.UUID, str]:
    user_id = uuid.uuid4()
    email = f"{ruolo.value}-{user_id.hex[:8]}@test.com"
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=ruolo,
                status=UserStatus.ACTIVE,
            )
        )
    return user_id, email


async def _login(api_client, email: str) -> dict:
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.json()


async def _refresh_row(tenant_id: uuid.UUID, plain: str) -> RefreshToken:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(plain))
        )
        return result.scalar_one()


@pytest.mark.e2e
async def test_disabilitare_con_patch_revoca_il_refresh_token(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    admin = {"Authorization": f"Bearer {await owner_token(api_client, tenant_id)}"}
    member_id, member_email = await _utente(tenant_id, UserRole.MEMBER)
    tokens = await _login(api_client, member_email)

    disabilita = await api_client.patch(
        f"/api/v1/users/{member_id}", json={"status": "disabled"}, headers=admin
    )
    assert disabilita.status_code == 200
    rifiutato = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rifiutato.status_code == 401

    # Riattivare non deve far rivivere la sessione di prima della disabilitazione.
    riattiva = await api_client.patch(
        f"/api/v1/users/{member_id}", json={"status": "active"}, headers=admin
    )
    assert riattiva.status_code == 200
    resp = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


@pytest.mark.e2e
async def test_logout_tutte_le_sessioni_non_lascia_vivo_il_successore_concorrente(
    api_client, two_tenants
):
    tenant_id, _ = two_tenants
    user_id, email = await _utente(tenant_id, UserRole.MEMBER)
    tokens = await _login(api_client, email)
    access = {"Authorization": f"Bearer {tokens['access_token']}"}
    family_id = (await _refresh_row(tenant_id, tokens["refresh_token"])).family_id

    # Una rotazione in corso tiene il lock sull'utente, come fa un refresh reale.
    # Il successore viene committato mentre il logout e in attesa.
    _, successore_plain = new_refresh_token()
    async with tenant_session(tenant_id) as rotazione:
        await rotazione.execute(select(User.id).where(User.id == user_id).with_for_update())
        logout = asyncio.create_task(
            api_client.post("/api/v1/auth/logout", json={"revoke_all": True}, headers=access)
        )
        await asyncio.sleep(0.3)
        rotazione.add(
            RefreshToken(
                tenant_id=tenant_id,
                user_id=user_id,
                token_hash=hash_token(successore_plain),
                jti=str(uuid.uuid4()),
                family_id=family_id,
                expires_at=(await _refresh_row(tenant_id, tokens["refresh_token"])).expires_at,
                revoked_at=None,
            )
        )
    resp = await logout
    assert resp.status_code == 204

    successore = await _refresh_row(tenant_id, successore_plain)
    assert successore.revoked_at is not None


@pytest.mark.e2e
async def test_refresh_e_rimozione_concorrenti_non_si_bloccano_a_vicenda(api_client, two_tenants):
    """Rimozione dell'owner: il tenant e bloccato FOR UPDATE, poi serve il
    refresh token. Un refresh che tenesse il token prima del tenant entrerebbe
    in deadlock (40P01) con questa transazione."""
    tenant_id, _ = two_tenants
    _, email = await _utente(tenant_id, UserRole.MEMBER)
    tokens = await _login(api_client, email)

    async with tenant_session(tenant_id) as rimozione:
        await rimozione.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        refresh = asyncio.create_task(
            api_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        )
        await asyncio.sleep(0.3)
        await rimozione.execute(
            select(RefreshToken.id)
            .where(RefreshToken.token_hash == hash_token(tokens["refresh_token"]))
            .with_for_update()
        )
    resp = await refresh
    assert resp.status_code == 200
