"""CLI di installazione e rete di sicurezza degli errori.

Due zone che si attraversano una volta sola ma quando servono devono funzionare:

  * `python -m app bootstrap` crea il primo tenant di un'istanza. Se si rompe,
    l'installazione e' morta e non c'e' nessuna dashboard da cui accorgersene
    (`app/cli.py` era al 46%, solo il ramo d'errore che ho aggiunto).
  * i gestori di eccezione di `app/main.py` (84%) trasformano una violazione di
    vincolo in 409 e qualunque altra cosa in un 500 che non racconta l'interno.
    Sono l'ultima linea: se cedono, l'errore esce con lo stack o con un 500 dove
    dovrebbe esserci un 409.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.db.session import async_session_factory_app, tenant_session
from app.db.types import UserRole, UserStatus
from app.main import create_app
from app.models.severity_preset import SeverityPreset
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "bootstrap-password-123"


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _nome_tenant() -> str:
    return f"Tenant {uuid.uuid4().hex[:8]}"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    """La CLI in un processo a parte, com'e' lanciata in produzione
    (`docker compose run --rm migrate python -m app.cli ...`).

    In-process non e' possibile: `bootstrap` chiama `asyncio.run()` e questi test
    girano dentro un event loop, con gli engine async legati a quello. Il
    sottoprocesso e' anche piu' fedele: prova davvero `python -m app`."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app", *args],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "ENV_FILE": ".env.test"},
    )


async def _tenant_per_nome(nome: str) -> Tenant:
    async with async_session_factory_app() as session:
        result = await session.execute(select(Tenant).where(Tenant.name == nome))
        return result.scalar_one()


# --- bootstrap ---------------------------------------------------------------


@pytest.mark.e2e
async def test_bootstrap_crea_tenant_owner_e_permette_il_login(api_client, migrated_db):
    """Il giro che fa ogni installazione nuova: CLI, poi login dalla dashboard."""
    nome = _nome_tenant()
    email = f"owner-{uuid.uuid4().hex[:8]}@acme-notifyhub.com"

    esito = _cli("bootstrap", "--tenant-name", nome, "--email", email, "--password", PASSWORD)
    assert esito.returncode == 0, esito.stderr
    assert "Tenant created" in esito.stdout
    assert "Owner created" in esito.stdout

    tenant = await _tenant_per_nome(nome)
    assert tenant.status == "active"
    # Lo slug del tenant nasce dal nome, minuscolo e senza spazi.
    assert tenant.slug == nome.lower().replace(" ", "-")

    async with tenant_session(tenant.id) as session:
        result = await session.execute(select(User).where(User.email == email))
        owner = result.scalar_one()
    assert owner.role == UserRole.OWNER
    assert owner.status == UserStatus.ACTIVE
    # La password non e' in chiaro: e' un hash Argon2id.
    assert owner.password_hash.startswith("$argon2")

    login = await api_client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    me = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.json()["role"] == "owner"
    assert me.json()["tenant_name"] == nome


@pytest.mark.e2e
async def test_bootstrap_installa_i_preset_del_catalogo(migrated_db):
    """Un tenant nuovo trova le regole pronte: se il bootstrap smettesse di
    installarle, ogni installazione nuova partirebbe senza nessuna regola e
    nessuno se ne accorgerebbe fino al primo messaggio non classificato."""
    nome = _nome_tenant()
    esito = _cli(
        "bootstrap",
        "--tenant-name",
        nome,
        "--email",
        f"owner-{uuid.uuid4().hex[:8]}@acme-notifyhub.com",
        "--password",
        PASSWORD,
    )
    assert esito.returncode == 0, esito.stderr

    tenant = await _tenant_per_nome(nome)
    async with tenant_session(tenant.id) as session:
        result = await session.execute(
            select(SeverityPreset).where(SeverityPreset.tenant_id == tenant.id)
        )
        preset = {p.builtin_key for p in result.scalars().all()}
    assert {"bash-generic", "postgres", "mongodb", "tar", "rclone"} <= preset


@pytest.mark.e2e
async def test_bootstrap_con_email_gia_registrata_non_lascia_meta_lavoro(migrated_db):
    """L'email e' unica globalmente: un secondo bootstrap con la stessa email deve
    fallire in modo pulito, non lasciare un tenant senza owner."""
    email = f"owner-{uuid.uuid4().hex[:8]}@acme-notifyhub.com"
    primo = _cli(
        "bootstrap", "--tenant-name", _nome_tenant(), "--email", email, "--password", PASSWORD
    )
    assert primo.returncode == 0, primo.stderr

    nome_secondo = _nome_tenant()
    secondo = _cli(
        "bootstrap", "--tenant-name", nome_secondo, "--email", email, "--password", PASSWORD
    )
    assert secondo.returncode != 0

    # Il tenant del secondo tentativo non deve restare in giro senza owner.
    async with async_session_factory_app() as session:
        result = await session.execute(select(Tenant).where(Tenant.name == nome_secondo))
        rimasto = result.scalar_one_or_none()
    if rimasto is not None:
        async with tenant_session(rimasto.id) as session:
            utenti = await session.execute(select(User).where(User.tenant_id == rimasto.id))
            assert list(utenti.scalars().all()), (
                "tenant creato senza owner: installazione inutilizzabile e invisibile"
            )


@pytest.mark.e2e
async def test_sync_presets_e_idempotente(migrated_db):
    """Si lancia dopo ogni aggiornamento che aggiunge preset: due esecuzioni di
    fila non devono duplicare niente."""
    primo = _cli("sync-presets")
    assert primo.returncode == 0, primo.stderr
    secondo = _cli("sync-presets")
    assert secondo.returncode == 0, secondo.stderr

    async with async_session_factory_app() as session:
        tenants = (await session.execute(select(Tenant.id))).scalars().all()
    for tenant_id in tenants:
        async with tenant_session(tenant_id) as session:
            result = await session.execute(
                select(SeverityPreset.builtin_key).where(
                    SeverityPreset.tenant_id == tenant_id,
                    SeverityPreset.builtin_key.isnot(None),
                )
            )
            chiavi = [row[0] for row in result.all()]
        assert len(chiavi) == len(set(chiavi)), f"preset duplicati nel tenant {tenant_id}"


# --- gestori di errore -------------------------------------------------------


@pytest.mark.e2e
async def test_violazione_di_unicita_diventa_409_non_500(api_client, two_tenants, owner_token):
    """Due gruppi con lo stesso nome nello stesso tenant violano
    `uq_groups_tenant_id_name`. Deve uscire un 409 con corpo RFC 7807, non un 500."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}
    nome = f"Gruppo {uuid.uuid4().hex[:8]}"

    primo = await api_client.post("/api/v1/groups", json={"name": nome}, headers=headers)
    assert primo.status_code == 201
    secondo = await api_client.post("/api/v1/groups", json={"name": nome}, headers=headers)

    assert secondo.status_code == 409
    corpo = secondo.json()
    assert corpo["type"].startswith("/problems/")
    assert corpo["status"] == 409
    # Il messaggio del database non deve uscire: nomi di vincoli e di colonne
    # sono dettagli interni.
    assert "uq_groups" not in secondo.text
    assert "psycopg" not in secondo.text


@pytest.mark.e2e
async def test_lo_stesso_nome_in_due_tenant_e_permesso(api_client, two_tenants, owner_token):
    """Il vincolo e' per tenant: due organizzazioni diverse devono poter chiamare
    "Produzione" il proprio gruppo."""
    tenant_a, tenant_b = two_tenants
    nome = f"Gruppo {uuid.uuid4().hex[:8]}"

    for tenant_id in (tenant_a, tenant_b):
        token = await owner_token(api_client, tenant_id)
        resp = await api_client.post(
            "/api/v1/groups",
            json={"name": nome},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201


@pytest.mark.e2e
async def test_eccezione_inattesa_esce_come_500_senza_dettagli(
    api_client, two_tenants, owner_token, monkeypatch
):
    """La rete di sicurezza: qualunque eccezione non prevista diventa un 500
    generico. Se cedesse, uscirebbero messaggi interni (nomi di tabelle, percorsi,
    valori) verso chiunque chiami l'API."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)

    def _esplode(*args, **kwargs):
        raise RuntimeError("segreto-che-non-deve-uscire")

    monkeypatch.setattr("app.api.v1.groups.accessible_group_ids", _esplode)

    # raise_app_exceptions=False: senza, l'eccezione arriva al test e il gestore
    # dell'applicazione non viene mai esercitato (e' il motivo per cui questo
    # caso era rimasto senza test veri).
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(), raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/groups", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 500
    assert "segreto-che-non-deve-uscire" not in resp.text
    corpo = resp.json()
    assert corpo["status"] == 500
    assert corpo["type"].startswith("/problems/")


@pytest.mark.e2e
async def test_id_malformato_e_422_non_500(api_client, two_tenants, owner_token):
    """Un UUID storto nel path e' un errore del chiamante, non del server."""
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    for percorso in (
        "/api/v1/groups/non-un-uuid",
        "/api/v1/receivers/non-un-uuid",
        "/api/v1/channels/non-un-uuid",
        "/api/v1/notifications/non-un-uuid",
    ):
        resp = await api_client.get(percorso, headers=headers)
        assert resp.status_code == 422, f"{percorso} -> {resp.status_code}"
        assert resp.json()["type"].startswith("/problems/")
