"""Indices, constraints, and triggers."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_notifications_body",
        "notifications",
        (
            "(storage_backend = 'inline' AND content IS NOT NULL AND storage_key IS NULL) "
            "OR (storage_backend = 'object' AND content IS NULL AND storage_key IS NOT NULL)"
        ),
    )

    op.create_index(
        "ix_notifications_tenant_id_received_at_id",
        "notifications",
        ["tenant_id", sa.desc("received_at"), sa.desc("id")],
    )
    op.create_index(
        "ix_notifications_tenant_id_receiver_id_received_at_id",
        "notifications",
        ["tenant_id", "receiver_id", sa.desc("received_at"), sa.desc("id")],
    )
    op.create_index(
        "ix_notifications_tenant_id_status",
        "notifications",
        ["tenant_id", "status"],
        postgresql_where="status = 'unread'",
    )
    op.create_index(
        "ix_notifications_content_preview_tsvector",
        "notifications",
        [sa.text("to_tsvector('simple', content_preview)")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_notifications_storage_key",
        "notifications",
        ["storage_key"],
        postgresql_where="storage_backend = 'object'",
    )

    op.create_index("ix_receivers_tenant_id_group_id", "receivers", ["tenant_id", "group_id"])

    op.create_index(
        "ix_severity_rules_tenant_id_receiver_id_priority",
        "severity_rules",
        ["tenant_id", "receiver_id", "priority"],
        postgresql_where="enabled = true",
    )

    op.create_index(
        "ix_deliveries_status_next_attempt_at",
        "deliveries",
        ["status", "next_attempt_at"],
        postgresql_where="status IN ('pending', 'failed')",
    )
    op.create_index(
        "ix_deliveries_status_locked_at",
        "deliveries",
        ["status", "locked_at"],
        postgresql_where="status = 'sending'",
    )
    op.create_index(
        "ix_deliveries_tenant_id_channel_id_status",
        "deliveries",
        ["tenant_id", "channel_id", "status"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table in [
        "tenants",
        "users",
        "groups",
        "receivers",
        "severity_rules",
        "delivery_channels",
        "group_channel_bindings",
        "receiver_channel_overrides",
    ]:
        op.execute(
            f"""
            CREATE TRIGGER {table}_updated_at_trigger
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION enqueue_object_deletion()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.storage_backend = 'object' THEN
                INSERT INTO pending_object_deletions (storage_key, enqueued_at, attempts)
                VALUES (OLD.storage_key, now(), 0);
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER notifications_enqueue_object_deletion
        AFTER DELETE ON notifications
        FOR EACH ROW
        EXECUTE FUNCTION enqueue_object_deletion();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS notifications_enqueue_object_deletion ON notifications")
    op.execute("DROP FUNCTION IF EXISTS enqueue_object_deletion()")

    for table in [
        "tenants",
        "users",
        "groups",
        "receivers",
        "severity_rules",
        "delivery_channels",
        "group_channel_bindings",
        "receiver_channel_overrides",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_updated_at_trigger ON {table}")

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    op.drop_index("ix_deliveries_tenant_id_channel_id_status", "deliveries")
    op.drop_index("ix_deliveries_status_locked_at", "deliveries")
    op.drop_index("ix_deliveries_status_next_attempt_at", "deliveries")

    op.drop_index("ix_severity_rules_tenant_id_receiver_id_priority", "severity_rules")

    op.drop_index("ix_receivers_tenant_id_group_id", "receivers")

    op.drop_index("ix_notifications_storage_key", "notifications")
    op.drop_index("ix_notifications_content_preview_tsvector", "notifications")
    op.drop_index("ix_notifications_tenant_id_status", "notifications")
    op.drop_index("ix_notifications_tenant_id_receiver_id_received_at_id", "notifications")
    op.drop_index("ix_notifications_tenant_id_received_at_id", "notifications")

    op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS ck_notifications_body")
