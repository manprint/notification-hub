"""Migrazione 0018: le descrizioni dei preset installati passano agli accenti giusti, e
solo dove sono ancora quelle di fabbrica del catalogo (v-receivers-05,
v-admin-presets-missing-accents).

Il test esegue upgrade e downgrade della revisione sul database di test, con dati veri.
Il tenant A ha un preset di fabbrica e uno modificato dall'utente, il tenant B ha
entrambi di fabbrica, e un preset senza chiave di catalogo resta com'e'. RLS e' forzata
anche per la migrazione: il test verifica che il cambio arrivi a ogni tenant, e non a un
insieme vuoto.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.db.sync_session import sync_session_factory, tenant_session_sync

_MIGRAZIONE = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0018_descrizioni_preset_con_accenti.py"
)
_MODIFICATA = "Descrizione scritta dall'utente, da non toccare."


def _carica_migrazione():
    spec = importlib.util.spec_from_file_location("migrazione_0018", _MIGRAZIONE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _inserisci(tenant_id, righe: list[tuple[str | None, str, str]]) -> None:
    with tenant_session_sync(tenant_id) as session:
        for chiave, nome, descrizione in righe:
            session.execute(
                text(
                    "INSERT INTO severity_presets (id, tenant_id, builtin_key, name, description)"
                    " VALUES (gen_random_uuid(), :tenant_id, :chiave, :nome, :descrizione)"
                ),
                {
                    "tenant_id": tenant_id,
                    "chiave": chiave,
                    "nome": nome,
                    "descrizione": descrizione,
                },
            )


def _descrizioni(tenant_id) -> dict[str, str]:
    with tenant_session_sync(tenant_id) as session:
        righe = session.execute(
            text("SELECT name, description FROM severity_presets WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).all()
    return {nome: descrizione for nome, descrizione in righe}


def _esegui(metodo: str) -> None:
    modulo = _carica_migrazione()
    with sync_session_factory() as session:
        contesto = MigrationContext.configure(connection=session.connection())
        with Operations.context(contesto):
            getattr(modulo, metodo)()
        session.commit()


@pytest.mark.integration
def test_upgrade_e_downgrade_toccano_solo_le_descrizioni_di_fabbrica(two_tenants):
    tenant_a, tenant_b = two_tenants
    modulo = _carica_migrazione()
    vecchia_pg = modulo._DESCRIZIONI_VECCHIE["postgres"]
    nuova_pg = modulo._DESCRIZIONI_NUOVE["postgres"]
    vecchia_mongo = modulo._DESCRIZIONI_VECCHIE["mongodb"]
    nuova_mongo = modulo._DESCRIZIONI_NUOVE["mongodb"]
    # Il testo di partenza e' quello del catalogo prima della correzione.
    assert "piu gli errori" in vecchia_pg
    assert "severita F/E/W" in vecchia_mongo
    assert "più gli errori" in nuova_pg
    assert "severità F/E/W" in nuova_mongo

    _inserisci(
        tenant_a,
        [
            ("postgres", "PostgreSQL", vecchia_pg),
            ("mongodb", "MongoDB", _MODIFICATA),
            (None, "Preset mio", vecchia_pg),
        ],
    )
    _inserisci(
        tenant_b,
        [
            ("postgres", "PostgreSQL", vecchia_pg),
            ("mongodb", "MongoDB", vecchia_mongo),
        ],
    )

    _esegui("upgrade")

    descrizioni_a = _descrizioni(tenant_a)
    assert descrizioni_a["PostgreSQL"] == nuova_pg
    assert descrizioni_a["MongoDB"] == _MODIFICATA  # modificata dall'utente: intatta
    assert descrizioni_a["Preset mio"] == vecchia_pg  # senza chiave di catalogo: intatta
    descrizioni_b = _descrizioni(tenant_b)
    assert descrizioni_b["PostgreSQL"] == nuova_pg
    assert descrizioni_b["MongoDB"] == nuova_mongo

    _esegui("downgrade")

    descrizioni_a = _descrizioni(tenant_a)
    assert descrizioni_a["PostgreSQL"] == vecchia_pg
    assert descrizioni_a["MongoDB"] == _MODIFICATA
    descrizioni_b = _descrizioni(tenant_b)
    assert descrizioni_b["PostgreSQL"] == vecchia_pg
    assert descrizioni_b["MongoDB"] == vecchia_mongo
