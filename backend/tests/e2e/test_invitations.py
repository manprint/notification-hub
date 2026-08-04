"""Ciclo di vita di un invito: e' la strada con cui entra ogni utente dopo il primo.

`POST /invitations/accept` era senza copertura: se si rompe, nessuno riesce piu' a
unirsi a un tenant e il guasto si scopre solo quando qualcuno prova.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db.session import tenant_session
from app.db.types import TenantStatus, UserRole, UserStatus
from app.models.invitation import Invitation
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "invito-password-123"


def _email() -> str:
    return f"invitato-{uuid.uuid4().hex[:10]}@acme-notifyhub.com"


async def _invita(api_client, headers, email: str, role: str = "member"):
    return await api_client.post(
        "/api/v1/invitations", json={"email": email, "role": role}, headers=headers
    )


def _token_da_url(invite_url: str) -> str:
    """Il token viaggia solo nel frammento (mai trasmesso al server, spec 9.2):
    la SPA lo estrae da li' e lo rimette nel corpo della POST."""
    assert "#token=" in invite_url, invite_url
    return invite_url.split("#token=", 1)[1]


@pytest.mark.e2e
async def test_giro_completo_invito_accettazione_login(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    email = _email()

    invito = await _invita(api_client, headers, email, "admin")
    assert invito.status_code == 201
    corpo = invito.json()
    assert corpo["email"] == email
    assert corpo["role"] == "admin"
    # Il link resta copiabile anche senza SMTP configurato: e' l'unico modo di
    # consegnare l'invito su un'istanza self-hosted senza posta.
    assert "/invite#token=" in corpo["invite_url"]

    accetta = await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": _token_da_url(corpo["invite_url"]), "password": PASSWORD},
    )
    assert accetta.status_code == 201
    assert accetta.json()["tenant_id"] == str(tenant_id)

    # L'utente nasce nel tenant giusto, col ruolo dell'invito e attivo.
    async with tenant_session(tenant_id) as session:
        result = await session.execute(select(User).where(User.email == email))
        utente = result.scalar_one()
    assert utente.role == UserRole.ADMIN
    assert utente.status == UserStatus.ACTIVE
    assert utente.tenant_id == tenant_id

    # E riesce ad autenticarsi con la password che ha scelto lui.
    login = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    me = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.json()["role"] == "admin"
    assert me.json()["tenant_id"] == str(tenant_id)


@pytest.mark.e2e
async def test_token_usa_e_getta(api_client, two_tenants, owner_token):
    """Un invito accettato due volte creerebbe due utenti con la stessa email (e
    violerebbe l'unicita' globale con un 500)."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    invito = await _invita(api_client, headers, _email())
    invite_token = _token_da_url(invito.json()["invite_url"])

    primo = await api_client.post(
        "/api/v1/invitations/accept", json={"token": invite_token, "password": PASSWORD}
    )
    assert primo.status_code == 201

    secondo = await api_client.post(
        "/api/v1/invitations/accept", json={"token": invite_token, "password": PASSWORD}
    )
    assert secondo.status_code == 401
    assert "already accepted" in secondo.text


@pytest.mark.e2e
async def test_token_inventato_rifiutato(api_client):
    resp = await api_client.post(
        "/api/v1/invitations/accept", json={"token": "token-inventato", "password": PASSWORD}
    )
    assert resp.status_code == 401


@pytest.mark.e2e
async def test_invito_scaduto_rifiutato(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    invito = await _invita(api_client, headers, _email())
    invite_token = _token_da_url(invito.json()["invite_url"])
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Invitation)
            .where(Invitation.id == uuid.UUID(invito.json()["id"]))
            .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
        )

    resp = await api_client.post(
        "/api/v1/invitations/accept", json={"token": invite_token, "password": PASSWORD}
    )
    assert resp.status_code == 401
    assert "expired" in resp.text


@pytest.mark.e2e
async def test_invito_revocato_non_si_accetta(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    invito = await _invita(api_client, headers, _email())
    invite_token = _token_da_url(invito.json()["invite_url"])

    revoca = await api_client.delete(f"/api/v1/invitations/{invito.json()['id']}", headers=headers)
    assert revoca.status_code == 204

    resp = await api_client.post(
        "/api/v1/invitations/accept", json={"token": invite_token, "password": PASSWORD}
    )
    assert resp.status_code == 401


@pytest.mark.e2e
async def test_email_gia_registrata_da_409_non_500(api_client, two_tenants, owner_token):
    """`users.email` e' unica globalmente: senza il controllo esplicito questo caso
    usciva come violazione di vincolo, cioe' 500."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    email = _email()

    primo = await _invita(api_client, headers, email)
    secondo = await _invita(api_client, headers, email)
    assert primo.status_code == 201

    await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": _token_da_url(primo.json()["invite_url"]), "password": PASSWORD},
    )
    doppio = await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": _token_da_url(secondo.json()["invite_url"]), "password": PASSWORD},
    )
    assert doppio.status_code == 409
    assert "already registered" in doppio.text


@pytest.mark.e2e
async def test_tenant_sospeso_blocca_laccettazione(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    invito = await _invita(api_client, headers, _email())
    invite_token = _token_da_url(invito.json()["invite_url"])

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(status=TenantStatus.SUSPENDED)
        )
    try:
        resp = await api_client.post(
            "/api/v1/invitations/accept", json={"token": invite_token, "password": PASSWORD}
        )
        assert resp.status_code == 401
    finally:
        async with tenant_session(tenant_id) as session:
            await session.execute(
                update(Tenant).where(Tenant.id == tenant_id).values(status=TenantStatus.ACTIVE)
            )


@pytest.mark.e2e
async def test_elenco_mostra_i_soli_inviti_ancora_da_accettare(
    api_client, two_tenants, owner_token
):
    """Contratto dell'endpoint, fissato qui: l'elenco e' la lista di cosa resta da
    fare, quindi gli inviti accettati escono di scena (`accepted_at IS NULL`). E il
    token non compare mai, nemmeno hashato: chi legge l'elenco non deve poter
    accettare l'invito di qualcun altro."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    pendente = await _invita(api_client, headers, _email())
    accettato = await _invita(api_client, headers, _email())
    await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": _token_da_url(accettato.json()["invite_url"]), "password": PASSWORD},
    )

    elenco = await api_client.get("/api/v1/invitations", headers=headers)
    assert elenco.status_code == 200
    ids = {v["id"] for v in elenco.json()}
    assert pendente.json()["id"] in ids
    assert accettato.json()["id"] not in ids
    assert "token" not in elenco.text


@pytest.mark.e2e
async def test_solo_owner_puo_invitare_un_owner(api_client, two_tenants, owner_token, make_user):
    """Un admin che potesse invitare owner si autopromuoverebbe passando da un
    secondo account."""
    from app.core.security import hash_password

    tenant_id, _ = two_tenants
    admin_email = _email()
    await make_user(tenant_id, admin_email, hash_password(PASSWORD))
    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(User).where(User.email == admin_email).values(role=UserRole.ADMIN)
        )
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": admin_email, "password": PASSWORD}
    )
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    come_admin = await _invita(api_client, admin_headers, _email(), "owner")
    assert come_admin.status_code == 403

    token = await owner_token(api_client, tenant_id)
    come_owner = await _invita(api_client, {"Authorization": f"Bearer {token}"}, _email(), "owner")
    assert come_owner.status_code == 201


@pytest.mark.e2e
async def test_invito_richiede_almeno_admin(api_client, two_tenants, make_user):
    from app.core.security import hash_password

    tenant_id, _ = two_tenants
    member_email = _email()
    await make_user(tenant_id, member_email, hash_password(PASSWORD))  # ruolo member
    login = await api_client.post(
        "/api/v1/auth/login", json={"email": member_email, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await _invita(api_client, headers, _email())
    assert resp.status_code == 403
