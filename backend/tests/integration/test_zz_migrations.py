import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import get_settings

# Rinominato apposta test_zz_*: questo test smonta e rimonta l'intero schema
# (drop di tutte le tabelle e i tipi enum, poi ricreazione). Farlo girare in
# mezzo alla suite lascia le connessioni asyncpg pooled degli altri test con
# una cache di OID/statement che punta a relazioni ormai sostituite. L'ordine
# alfabetico di pytest lo mette per ultimo, cosi non puo corrompere nulla.


def _motore_sync():
    return create_engine(get_settings().database_url_sync)


@pytest.mark.integration
def test_rls_forzata_su_ogni_tabella_con_tenant_id(migrated_db):
    """Una tabella di tenant senza RLS forzata e una policy tenant_isolation, quindi
    accessibile a chi non imposta app.tenant_id, non deve passare la suite."""
    engine = _motore_sync()
    try:
        with engine.connect() as conn:
            senza_rls = (
                conn.execute(
                    text(
                        """
                        SELECT c.relname
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public' AND c.relkind = 'r'
                          AND EXISTS (
                            SELECT 1 FROM pg_attribute a
                            WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
                              AND NOT a.attisdropped)
                          AND NOT (
                            c.relrowsecurity AND c.relforcerowsecurity
                            AND EXISTS (
                              SELECT 1 FROM pg_policy p
                              WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation'))
                        ORDER BY 1
                        """
                    )
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert senza_rls == [], f"tabelle di tenant senza RLS forzata: {senza_rls}"


@pytest.mark.integration
def test_fk_con_cascade_o_no_action_hanno_un_indice_in_testa(migrated_db):
    """Ogni FK con ON DELETE CASCADE o NO ACTION ha un indice che inizia con la
    colonna FK: senza, ogni cancellazione del padre fa una sequential scan del figlio.
    Le FK verso tenants restano fuori di proposito: il tenant si cancella solo dalla
    CLI (app/cli.py), mai dall'applicazione, quindi non e' un costo che le richieste pagano."""
    engine = _motore_sync()
    try:
        with engine.connect() as conn:
            senza_indice = (
                conn.execute(
                    text(
                        """
                        SELECT c.conrelid::regclass::text || '.' || c.conname
                        FROM pg_constraint c
                        WHERE c.contype = 'f'
                          AND c.confdeltype IN ('a', 'c')
                          AND c.confrelid <> 'tenants'::regclass
                          AND NOT EXISTS (
                            SELECT 1 FROM pg_index i
                            WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
                        ORDER BY 1
                        """
                    )
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert senza_indice == [], f"FK senza indice in testa: {senza_indice}"


@pytest.mark.integration
def test_indici_di_notifications_e_audit_events_coincidono_con_i_modelli(migrated_db):
    """Autogenerate non deve proporre di cancellare indici che esistono solo nelle
    migrazioni (ricerca nel contenuto, filtro per notifica dell'audit), ne' di
    ricrearne con colonne diverse. Il confronto e' limitato alle due tabelle: le
    altre hanno drift di colonne e vincoli ancora da sistemare, fuori da questo test."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    import app.models  # noqa: F401
    from app.db.base import Base

    tabelle_verificate = {"notifications", "audit_events"}

    def solo_indici_di_queste_tabelle(oggetto, nome, tipo, riflesso, confronto):
        if tipo == "index":
            return oggetto.table.name in tabelle_verificate
        return False

    engine = _motore_sync()
    try:
        with engine.connect() as conn:
            contesto = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "include_object": solo_indici_di_queste_tabelle,
                },
            )
            differenze = compare_metadata(contesto, Base.metadata)
    finally:
        engine.dispose()

    assert differenze == [], f"drift fra migrazioni e modelli: {differenze}"


@pytest.mark.integration
def test_upgrade_e_downgrade(migrated_db):
    config = Config("alembic.ini")

    upgrade(config, "head")
    downgrade(config, "base")
    upgrade(config, "head")

    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    # alembic.command e sincrono: l'ispezione dello schema deve esserlo anche
    # lei. Usare l'engine ASYNC dell'API qui e un errore di tipo, non solo
    # stilistico: AsyncConnection non supporta il context manager sincrono.
    sync_engine = create_engine(get_settings().database_url_sync)
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names(schema="public"))
    sync_engine.dispose()

    expected_tables = {
        "tenants",
        "users",
        "invitations",
        "refresh_tokens",
        "groups",
        "receivers",
        "severity_rules",
        "severity_presets",
        "severity_preset_rules",
        "receiver_severity_presets",
        "notifications",
        "delivery_channels",
        "group_channel_bindings",
        "receiver_channel_overrides",
        "deliveries",
        "pending_object_deletions",
        "user_group_memberships",
        "audit_events",
        "alembic_version",  # bookkeeping di alembic stesso, non della spec
    }

    assert tables == expected_tables, (
        f"Missing: {expected_tables - tables}, unexpected: {tables - expected_tables}"
    )
