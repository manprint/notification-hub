import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config


@pytest.mark.integration
@pytest.mark.skip(reason="Alembic upgrade/downgrade requires synchronous engine setup")
def test_upgrade_e_downgrade(migrated_db):
    config = Config("alembic.ini")

    upgrade(config, "head")

    downgrade(config, "base")

    upgrade(config, "head")

    from sqlalchemy import inspect

    from app.db.session import engine_app

    with engine_app.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names(schema="public"))

    expected_tables = {
        "tenants",
        "users",
        "invitations",
        "refresh_tokens",
        "groups",
        "receivers",
        "severity_rules",
        "notifications",
        "delivery_channels",
        "group_channel_bindings",
        "receiver_channel_overrides",
        "deliveries",
        "pending_object_deletions",
    }

    assert tables == expected_tables, f"Missing tables: {expected_tables - tables}"
