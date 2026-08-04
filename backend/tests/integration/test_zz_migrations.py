import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config

# Rinominato apposta test_zz_*: questo test smonta e rimonta l'intero schema
# (drop di tutte le tabelle e i tipi enum, poi ricreazione). Farlo girare in
# mezzo alla suite lascia le connessioni asyncpg pooled degli altri test con
# una cache di OID/statement che punta a relazioni ormai sostituite. L'ordine
# alfabetico di pytest lo mette per ultimo, cosi non puo corrompere nulla.


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
        "alembic_version",  # bookkeeping di alembic stesso, non della spec
    }

    assert tables == expected_tables, (
        f"Missing: {expected_tables - tables}, unexpected: {tables - expected_tables}"
    )
