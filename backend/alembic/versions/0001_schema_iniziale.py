"""Initial schema: 13 tables, enums, citext extension."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.db.types import (
    channel_type_type,
    delivery_status_type,
    notification_status_type,
    override_mode_type,
    receiver_status_type,
    severity_source_type,
    severity_type,
    storage_backend_type,
    tenant_status_type,
    user_role_type,
    user_status_type,
)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Le colonne enum sotto importano gli stessi oggetti _type di app/db/types.py invece
# di ridichiarare l'enum: cosi l'unica fonte di verita per l'associazione fra i nomi
# dei membri Python e le label Postgres (minuscole, non i nomi maiuscoli dei membri)
# resta values_callable in app/db/types.py.
_ENUM_TYPES = [
    tenant_status_type,
    user_role_type,
    user_status_type,
    receiver_status_type,
    severity_type,
    severity_source_type,
    notification_status_type,
    storage_backend_type,
    channel_type_type,
    override_mode_type,
    delivery_status_type,
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    bind = op.get_bind()
    for enum_type in _ENUM_TYPES:
        enum_type.create(bind=bind, checkfirst=True)

    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("max_body_bytes", sa.Integer(), nullable=False),
        sa.Column("max_notifications_per_day", sa.Integer(), nullable=True),
        sa.Column("max_storage_bytes", sa.BigInteger(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("status", tenant_status_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", user_role_type, nullable=False),
        sa.Column("status", user_status_type, nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", user_role_type, nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_table(
        "groups",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_groups_tenant_id_name"),
    )

    op.create_table(
        "receivers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(22), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", receiver_status_type, nullable=False),
        sa.Column("ingestion_module", sa.String(), nullable=False),
        sa.Column("default_severity", severity_type, nullable=False),
        sa.Column("max_body_bytes", sa.Integer(), nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "severity_rules",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("receiver_id", sa.UUID(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(200), nullable=False),
        sa.Column("case_insensitive", sa.Boolean(), nullable=False),
        sa.Column("severity", severity_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["receiver_id"], ["receivers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("receiver_id", sa.UUID(), nullable=False),
        sa.Column("storage_backend", storage_backend_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("content_preview", sa.String(4096), nullable=False),
        sa.Column("content_size", sa.Integer(), nullable=False),
        sa.Column("content_normalized", sa.Boolean(), nullable=False),
        sa.Column("severity", severity_type, nullable=False),
        sa.Column("severity_source", severity_source_type, nullable=False),
        sa.Column("status", notification_status_type, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ip", sa.String(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["receiver_id"], ["receivers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "delivery_channels",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", channel_type_type, nullable=False),
        sa.Column("webhook_url", sa.LargeBinary(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "group_channel_bindings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("min_severity", severity_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["delivery_channels.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "channel_id", name="uq_group_channel_bindings_group_id_channel_id"
        ),
    )

    op.create_table(
        "receiver_channel_overrides",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("receiver_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("mode", override_mode_type, nullable=False),
        sa.Column("min_severity", severity_type, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["delivery_channels.id"]),
        sa.ForeignKeyConstraint(["receiver_id"], ["receivers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receiver_id", "channel_id", name="uq_receiver_channel_overrides_receiver_id_channel_id"
        ),
    )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("status", delivery_status_type, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["delivery_channels.id"]),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id", "channel_id", name="uq_deliveries_notification_id_channel_id"
        ),
    )

    op.create_table(
        "pending_object_deletions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pending_object_deletions")
    op.drop_table("deliveries")
    op.drop_table("receiver_channel_overrides")
    op.drop_table("group_channel_bindings")
    op.drop_table("delivery_channels")
    op.drop_table("notifications")
    op.drop_table("severity_rules")
    op.drop_table("receivers")
    op.drop_table("groups")
    op.drop_table("refresh_tokens")
    op.drop_table("invitations")
    op.drop_table("users")
    op.drop_table("tenants")

    bind = op.get_bind()
    for enum_type in reversed(_ENUM_TYPES):
        enum_type.drop(bind=bind, checkfirst=True)

    op.execute("DROP EXTENSION IF EXISTS citext")
