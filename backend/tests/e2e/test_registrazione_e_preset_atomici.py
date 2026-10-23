"""Registrazione atomica e sync dei preset predefiniti (c-be-api-03, c-be-api-04).

- La registrazione scrive tenant, owner e preset nella stessa transazione: un
  errore sui preset non lascia un account senza preset, e il retry non trova
  un'email gia registrata.
- Due sync dei preset concorrenti non fanno scattare il vincolo unico: il secondo
  aspetta il primo e poi vede i preset gia installati.
"""

import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from app.api.v1 import auth as auth_module
from app.db.session import async_session_factory_app, tenant_session
from app.main import create_app
from app.models.severity_preset import SeverityPreset
from app.models.tenant import Tenant
from app.models.user import User
from app.services import severity_presets
from app.services.severity_presets import BUILTIN_PRESETS, sync_builtin_presets


async def _registra(client: httpx.AsyncClient, nome: str, email: str) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/register",
        json={"tenant_name": nome, "email": email, "password": "x" * 12},
    )


@pytest.mark.e2e
async def test_errore_sui_preset_non_lascia_tenant_ne_owner(monkeypatch):
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(allow_public_registration=True),
    )
    sync_reale = severity_presets.sync_builtin_presets
    chiamate = {"n": 0}

    async def _primo_tentativo_guasto(session, tenant_id):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            raise RuntimeError("preset non installabile")
        return await sync_reale(session, tenant_id)

    monkeypatch.setattr(severity_presets, "sync_builtin_presets", _primo_tentativo_guasto)
    nome = f"Atomico {uuid.uuid4().hex[:8]}"
    email = f"atomico-{uuid.uuid4().hex[:8]}@test.com"
    # raise_app_exceptions=False: il 500 arriva come risposta, cosi' il test vede lo
    # stato del database dopo l'errore invece di un'eccezione del client.
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        primo = await _registra(client, nome, email)
        assert primo.status_code == 500

        async with async_session_factory_app() as session:
            tenant_id = (
                await session.execute(select(Tenant.id).where(Tenant.name == nome))
            ).scalar_one_or_none()
        assert tenant_id is None

        # Il retry non trova un account gia registrato: la registrazione va a buon fine
        # con il suo tenant, owner e preset.
        secondo = await _registra(client, nome, email)
        assert secondo.status_code == 201, secondo.text

    async with async_session_factory_app() as session:
        tenant_id = (
            await session.execute(select(Tenant.id).where(Tenant.name == nome))
        ).scalar_one()
    async with tenant_session(tenant_id) as session:
        utenti = (
            await session.execute(select(User.email).where(User.tenant_id == tenant_id))
        ).all()
        preset = (
            await session.execute(
                select(SeverityPreset.builtin_key).where(SeverityPreset.tenant_id == tenant_id)
            )
        ).all()
    assert [riga[0] for riga in utenti] == [email]
    assert {riga[0] for riga in preset} == {spec.key for spec in BUILTIN_PRESETS}


@pytest.mark.integration
async def test_due_sync_concorrenti_dei_preset_non_danno_errore(two_tenants):
    tenant_id, _ = two_tenants

    async def _sync() -> list[str]:
        async with tenant_session(tenant_id) as session:
            return await sync_builtin_presets(session, tenant_id)

    # Il primo sync installa tutto ma non committa: il secondo parte mentre il primo
    # tiene il lock del tenant. Senza il lock leggerebbe un insieme vuoto e il suo
    # INSERT resterebbe in attesa del vincolo unico, che poi fallisce con 409.
    async with tenant_session(tenant_id) as primo:
        await sync_builtin_presets(primo, tenant_id)
        secondo = asyncio.create_task(_sync())
        await asyncio.sleep(0.5)
    installati_dal_secondo = await asyncio.wait_for(secondo, timeout=10)

    assert installati_dal_secondo == []
    # severity_presets ha RLS: si conta dentro la sessione del tenant.
    async with tenant_session(tenant_id) as session:
        conteggio = await session.execute(
            select(func.count())
            .select_from(SeverityPreset)
            .where(SeverityPreset.tenant_id == tenant_id)
        )
    assert conteggio.scalar_one() == len(BUILTIN_PRESETS)
