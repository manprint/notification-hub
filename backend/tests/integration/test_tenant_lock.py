"""Il lock delle impostazioni del tenant non ferma gli INSERT dei figli (c-be-api-06).

Una scrittura di impostazioni (receiver con cap, PATCH /tenant) tiene il lock sulla
riga del tenant per tutta la sua transazione. Ogni INSERT su una tabella con FK verso
tenants prende FOR KEY SHARE su quella riga: con FOR UPDATE pieno i due si
bloccavano, e l'ingestion del tenant restava ferma. Con FOR NO KEY UPDATE no.

Il secondo test e' il controllo: col FOR UPDATE pieno il figlio resta bloccato, cosi'
il primo non passa per caso.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import tenant_session
from app.services.tenant_lock import lock_tenant_settings


async def _inserisci_figlio_del_tenant(session, tenant_id: uuid.UUID) -> None:
    # severity_presets ha la FK su tenants, come notifications e deliveries: il suo
    # INSERT prende FOR KEY SHARE sulla riga del tenant. Il timeout rende l'attesa
    # un errore leggibile invece di un test che non finisce.
    await session.execute(text("SET LOCAL lock_timeout = '2s'"))
    await session.execute(
        text(
            "INSERT INTO severity_presets (id, tenant_id, name, description)"
            " VALUES (gen_random_uuid(), :tenant_id, :name, '')"
        ),
        {"tenant_id": tenant_id, "name": f"preset-{uuid.uuid4().hex}"},
    )


@pytest.mark.integration
async def test_lock_impostazioni_non_blocca_l_insert_del_figlio(two_tenants):
    tenant_id, _ = two_tenants

    async with tenant_session(tenant_id) as impostazioni:
        await lock_tenant_settings(impostazioni, tenant_id)
        # Una seconda transazione dello stesso tenant, mentre la prima tiene il lock.
        async with tenant_session(tenant_id) as ingestione:
            await _inserisci_figlio_del_tenant(ingestione, tenant_id)


@pytest.mark.integration
async def test_for_update_pieno_blocca_l_insert_del_figlio(two_tenants):
    """Controllo: con il lock pieno l'INSERT del figlio non passa."""
    tenant_id, _ = two_tenants

    async with tenant_session(tenant_id) as impostazioni:
        await impostazioni.execute(
            text("SELECT id FROM tenants WHERE id = :tenant_id FOR UPDATE"),
            {"tenant_id": tenant_id},
        )
        with pytest.raises(DBAPIError) as exc_info:
            async with tenant_session(tenant_id) as ingestione:
                await _inserisci_figlio_del_tenant(ingestione, tenant_id)

    # 55P03 = lock_not_available: il timeout e' scattato sul lock della riga del tenant.
    assert getattr(exc_info.value.orig, "sqlstate", None) == "55P03"
