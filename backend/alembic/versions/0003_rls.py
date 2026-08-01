"""RLS policies and role grants."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        GRANT USAGE ON SCHEMA public TO notifyhub_app, notifyhub_ingest, notifyhub_auth;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO notifyhub_app;
        GRANT SELECT ON users, refresh_tokens, invitations TO notifyhub_auth;
        GRANT SELECT ON receivers TO notifyhub_ingest;
        """
    )

    for table in [
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
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
            """
        )

    op.execute(
        """
        CREATE POLICY ingest_slug_lookup ON receivers
        FOR SELECT TO notifyhub_ingest USING (true);
        """
    )

    for table in ["users", "refresh_tokens", "invitations"]:
        op.execute(
            f"""
            CREATE POLICY auth_lookup ON {table}
            FOR SELECT TO notifyhub_auth USING (true);
            """
        )


def downgrade() -> None:
    for table in ["users", "refresh_tokens", "invitations"]:
        op.execute(f"DROP POLICY IF EXISTS auth_lookup ON {table};")

    op.execute("DROP POLICY IF EXISTS ingest_slug_lookup ON receivers;")

    for table in [
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
    ]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute(
        """
        REVOKE SELECT ON users, refresh_tokens, invitations FROM notifyhub_auth;
        REVOKE SELECT ON receivers FROM notifyhub_ingest;
        REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM notifyhub_app;
        REVOKE USAGE ON SCHEMA public FROM notifyhub_app, notifyhub_ingest, notifyhub_auth;
        """
    )
