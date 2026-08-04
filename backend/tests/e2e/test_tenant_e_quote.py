"""Impostazioni del tenant e quote: i numeri che spengono l'ingestion.

`app/api/v1/tenant.py` era al 48% e `app/services/quota.py` al 71%: entrambi
decidono se una notifica entra o viene rifiutata con 429. Sono i due posti dove un
errore non si vede in dashboard, si vede sui job che smettono di riuscire a
parlare.
"""

import uuid

import pytest
from sqlalchemy import update

from app.db.session import tenant_session
from app.db.types import UserRole
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "tenant-password-123"


async def _headers(api_client, owner_token, tenant_id) -> dict[str, str]:
    token = await owner_token(api_client, tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _utente_con_ruolo(api_client, make_user, tenant_id, ruolo: UserRole) -> dict[str, str]:
    from app.core.security import hash_password

    email = f"{ruolo.value}-{uuid.uuid4().hex[:8]}@acme-notifyhub.com"
    await make_user(tenant_id, email, hash_password(PASSWORD))
    async with tenant_session(tenant_id) as session:
        await session.execute(update(User).where(User.email == email).values(role=ruolo))
    login = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- lettura e modifica ------------------------------------------------------


@pytest.mark.e2e
async def test_lettura_delle_impostazioni(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)

    resp = await api_client.get("/api/v1/tenant", headers=headers)
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["id"] == str(tenant_id)
    # Il contratto dei campi: la dashboard e docs/OPERAZIONI.md ci contano.
    assert set(corpo) == {
        "id",
        "name",
        "slug",
        "max_body_bytes",
        "max_notifications_per_day",
        "max_storage_bytes",
        "retention_days",
        "status",
    }


@pytest.mark.e2e
async def test_modifica_di_retention_e_quote(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)

    resp = await api_client.patch(
        "/api/v1/tenant",
        json={
            "name": "ACME rinominata",
            "retention_days": 30,
            "max_notifications_per_day": 5000,
            "max_storage_bytes": 10_000_000,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["name"] == "ACME rinominata"
    assert corpo["retention_days"] == 30
    assert corpo["max_notifications_per_day"] == 5000
    assert corpo["max_storage_bytes"] == 10_000_000

    # Riletto: la modifica e' persistita, non solo restituita.
    riletto = await api_client.get("/api/v1/tenant", headers=headers)
    assert riletto.json()["retention_days"] == 30


@pytest.mark.e2e
@pytest.mark.parametrize(
    "corpo",
    [
        {"max_body_bytes": 0},  # sotto il minimo
        {"max_body_bytes": 20_971_521},  # oltre l'hard limit di sistema (20MB)
        {"retention_days": 0},
        {"max_notifications_per_day": 0},
        {"max_storage_bytes": 0},
        {"name": ""},
    ],
)
async def test_valori_fuori_dominio_rifiutati(api_client, two_tenants, owner_token, corpo):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    resp = await api_client.patch("/api/v1/tenant", json=corpo, headers=headers)
    assert resp.status_code == 422, f"{corpo} accettato"


@pytest.mark.e2e
async def test_solo_lowner_cambia_le_impostazioni(api_client, two_tenants, owner_token, make_user):
    """Retention e quote decidono cosa si perde e cosa entra: restano all'owner
    anche se l'admin gestisce utenti e configurazione dell'inoltro."""
    tenant_id, _ = two_tenants

    for ruolo in (UserRole.ADMIN, UserRole.MEMBER, UserRole.VIEWER):
        headers = await _utente_con_ruolo(api_client, make_user, tenant_id, ruolo)
        resp = await api_client.patch("/api/v1/tenant", json={"retention_days": 7}, headers=headers)
        assert resp.status_code == 403, f"{ruolo.value} ha potuto modificare il tenant"


@pytest.mark.e2e
async def test_le_impostazioni_di_un_altro_tenant_non_si_vedono(
    api_client, two_tenants, owner_token
):
    tenant_a, tenant_b = two_tenants
    headers_a = await _headers(api_client, owner_token, tenant_a)
    headers_b = await _headers(api_client, owner_token, tenant_b)

    a = await api_client.get("/api/v1/tenant", headers=headers_a)
    b = await api_client.get("/api/v1/tenant", headers=headers_b)
    # L'endpoint non prende id: legge sempre e solo il tenant del chiamante.
    assert a.json()["id"] == str(tenant_a)
    assert b.json()["id"] == str(tenant_b)


# --- quote in ingestion ------------------------------------------------------


async def _receiver_con_slug(api_client, headers) -> dict:
    gruppo = await api_client.post(
        "/api/v1/groups", json={"name": f"Quote {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    resp = await api_client.post(
        f"/api/v1/groups/{gruppo.json()['id']}/receivers",
        json={"name": "job"},
        headers=headers,
    )
    return resp.json()


@pytest.mark.e2e
async def test_quota_giornaliera_esaurita_rifiuta_con_429(api_client, two_tenants, owner_token):
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    receiver = await _receiver_con_slug(api_client, headers)

    primo = await api_client.post(f"/ingest/{receiver['slug']}", content="prima")
    assert primo.status_code == 201

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(max_notifications_per_day=1)
        )
    try:
        rifiutato = await api_client.post(f"/ingest/{receiver['slug']}", content="seconda")
        assert rifiutato.status_code == 429
        assert "quota" in rifiutato.text.lower()
    finally:
        async with tenant_session(tenant_id) as session:
            await session.execute(
                update(Tenant).where(Tenant.id == tenant_id).values(max_notifications_per_day=None)
            )


@pytest.mark.e2e
async def test_quota_di_spazio_esaurita_rifiuta_con_429(api_client, two_tenants, owner_token):
    """Il ramo di `max_storage_bytes` non era coperto: e' quello che protegge il
    disco, e se sbagliasse verso non bloccherebbe mai (disco pieno) o bloccherebbe
    sempre (istanza muta)."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    receiver = await _receiver_con_slug(api_client, headers)

    await api_client.post(f"/ingest/{receiver['slug']}", content="x" * 500)

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant_id).values(max_storage_bytes=600)
        )
    try:
        rifiutato = await api_client.post(f"/ingest/{receiver['slug']}", content="y" * 500)
        assert rifiutato.status_code == 429
        assert "storage" in rifiutato.text.lower()
    finally:
        async with tenant_session(tenant_id) as session:
            await session.execute(
                update(Tenant).where(Tenant.id == tenant_id).values(max_storage_bytes=None)
            )


@pytest.mark.e2e
async def test_quote_a_null_sono_illimitate(api_client, two_tenants, owner_token):
    """NULL = illimitato (spec 4.1): un tenant appena creato non deve avere limiti
    nascosti."""
    tenant_id, _ = two_tenants
    headers = await _headers(api_client, owner_token, tenant_id)
    receiver = await _receiver_con_slug(api_client, headers)

    async with tenant_session(tenant_id) as session:
        await session.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(max_notifications_per_day=None, max_storage_bytes=None)
        )

    for i in range(3):
        resp = await api_client.post(f"/ingest/{receiver['slug']}", content=f"messaggio {i}")
        assert resp.status_code == 201
