"""Login e registrazione: limiti, tempi e atomicita (spec 10.2).

Il 401 del login e uniforme di proposito: questi test verificano che il resto del
comportamento non tradisca l'esistenza di un'email o di un tenant sospeso.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from app.api.v1 import auth as auth_module
from app.core.security import hash_password
from app.db.session import async_session_factory_app, engine_app, tenant_session
from app.db.types import UserRole, UserStatus
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "correct-horse-battery"


async def _utente(tenant_id: uuid.UUID, email: str, ruolo: UserRole = UserRole.MEMBER) -> None:
    async with tenant_session(tenant_id) as session:
        session.add(
            User(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=ruolo,
                status=UserStatus.ACTIVE,
            )
        )


@pytest.mark.e2e
async def test_limite_di_login_non_si_aggira_cambiando_maiuscole_nell_email(api_client):
    # Il conteggio e per (email, IP): due grafie dello stesso indirizzo condividono
    # lo stesso account, quindi devono condividere anche il contatore.
    email_mista = f"Admin{uuid.uuid4().hex[:8]}@corp.example.com"
    for _ in range(10):
        resp = await api_client.post(
            "/api/v1/auth/login", json={"email": email_mista, "password": "password-sbagliata-1"}
        )
        assert resp.status_code == 401

    resp = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email_mista.lower(), "password": "password-sbagliata-1"},
    )
    assert resp.status_code == 429
    assert resp.json()["retry_after"] >= 1


@pytest.mark.e2e
async def test_email_sconosciuta_esegue_comunque_una_verifica_argon2(api_client, monkeypatch):
    # Senza questa verifica il ramo "email sconosciuta" risponde in ~1 ms e quello
    # con email registrata in centinaia di ms: il 401 uniforme diventerebbe un
    # oracolo sull'esistenza dell'account.
    chiamate: list[str] = []
    originale = auth_module.verify_password

    def spia(password: str, hash_value: str) -> bool:
        chiamate.append(hash_value)
        return originale(password, hash_value)

    monkeypatch.setattr(auth_module, "verify_password", spia)
    resp = await api_client.post(
        "/api/v1/auth/login",
        json={"email": f"nessuno-{uuid.uuid4().hex}@test.com", "password": "password-qualunque-1"},
    )
    assert resp.status_code == 401
    assert len(chiamate) == 1


@pytest.mark.e2e
async def test_login_tenant_sospeso_scrive_l_audit_fuori_dalla_sessione_del_tenant(
    api_client, two_tenants, owner_conn, monkeypatch
):
    # Il rifiuto per tenant sospeso apriva l'audit mentre la sessione del login
    # teneva ancora la sua connessione: con il pool esaurito le due attese si
    # bloccavano a vicenda. Il rifiuto deve avvenire con nessuna connessione
    # del login ancora aperta.
    tenant_id, _ = two_tenants
    await owner_conn.execute(
        text("UPDATE tenants SET status = 'suspended' WHERE id = :id"), {"id": tenant_id}
    )
    await owner_conn.commit()
    email = f"sospeso-{uuid.uuid4().hex[:8]}@test.com"
    await _utente(tenant_id, email)

    misurazioni: list[tuple[str, int]] = []
    originale = auth_module._record_login_failure

    async def spia(user_identity, request, reason: str) -> None:
        misurazioni.append((reason, engine_app.pool.checkedout()))
        await originale(user_identity, request, reason)

    monkeypatch.setattr(auth_module, "_record_login_failure", spia)
    base = engine_app.pool.checkedout()
    resp = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 401
    assert misurazioni == [("tenant_suspended", base)]


@pytest.mark.e2e
async def test_registrazione_con_email_gia_presa_non_lascia_tenant_orfano(
    api_client, two_tenants, monkeypatch
):
    # Simula la corsa: il controllo preliminare non vede l'utente, ma l'INSERT
    # dell'owner viola il vincolo unico. Il tenant non deve restare senza utenti.
    tenant_id, _ = two_tenants
    email = f"doppio-{uuid.uuid4().hex[:8]}@test.com"
    await _utente(tenant_id, email, UserRole.OWNER)

    async def nessuno(_email: str) -> None:
        return None

    monkeypatch.setattr(auth_module, "find_user_by_email", nessuno)
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(allow_public_registration=True),
    )
    nome = f"Fantasma {uuid.uuid4().hex[:8]}"
    resp = await api_client.post(
        "/api/v1/auth/register",
        json={"tenant_name": nome, "email": email, "password": "x" * 12},
    )
    assert resp.status_code == 409

    async with async_session_factory_app() as session:
        rimasti = (await session.execute(select(Tenant).where(Tenant.name == nome))).scalars()
        assert list(rimasti) == []
