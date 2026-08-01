"""Initial schema: 13 tables, enums, citext extension."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.db.types import (
    ChannelType,
    DeliveryStatus,
    NotificationStatus,
    OverrideMode,
    ReceiverStatus,
    Severity,
    SeveritySource,
    StorageBackend,
    TenantStatus,
    UserRole,
    UserStatus,
)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute(sa.Enum(TenantStatus, name="tenant_status").create(bind=op.get_bind()))
    op.execute(sa.Enum(UserRole, name="user_role").create(bind=op.get_bind()))
    op.execute(sa.Enum(UserStatus, name="user_status").create(bind=op.get_bind()))
    op.execute(sa.Enum(ReceiverStatus, name="receiver_status").create(bind=op.get_bind()))
    op.execute(sa.Enum(Severity, name="severity").create(bind=op.get_bind()))
    op.execute(sa.Enum(SeveritySource, name="severity_source").create(bind=op.get_bind()))
    op.execute(sa.Enum(NotificationStatus, name="notification_status").create(bind=op.get_bind()))
    op.execute(sa.Enum(StorageBackend, name="storage_backend").create(bind=op.get_bind()))
    op.execute(sa.Enum(ChannelType, name="channel_type").create(bind=op.get_bind()))
    op.execute(sa.Enum(OverrideMode, name="override_mode").create(bind=op.get_bind()))
    op.execute(sa.Enum(DeliveryStatus, name="delivery_status").create(bind=op.get_bind()))

    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("max_body_bytes", sa.Integer(), nullable=False),
        sa.Column("max_notifications_per_day", sa.Integer(), nullable=True),
        sa.Column("max_storage_bytes", sa.BigInteger(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("status", postgresql.ENUM(TenantStatus, name="tenant_status"), nullable=False),
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
        sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", postgresql.ENUM(UserRole, name="user_role"), nullable=False),
        sa.Column("status", postgresql.ENUM(UserStatus, name="user_status"), nullable=False),
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
        sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=False),
        sa.Column("role", postgresql.ENUM(UserRole, name="user_role"), nullable=False),
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
        sa.Column(
            "status", postgresql.ENUM(ReceiverStatus, name="receiver_status"), nullable=False
        ),
        sa.Column("ingestion_module", sa.String(), nullable=False),
        sa.Column("default_severity", postgresql.ENUM(Severity, name="severity"), nullable=False),
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
        sa.Column("severity", postgresql.ENUM(Severity, name="severity"), nullable=False),
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
        sa.Column(
            "storage_backend",
            postgresql.ENUM(StorageBackend, name="storage_backend"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("content_preview", sa.String(4096), nullable=False),
        sa.Column("content_size", sa.Integer(), nullable=False),
        sa.Column("content_normalized", sa.Boolean(), nullable=False),
        sa.Column("severity", postgresql.ENUM(Severity, name="severity"), nullable=False),
        sa.Column(
            "severity_source",
            postgresql.ENUM(SeveritySource, name="severity_source"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(NotificationStatus, name="notification_status"),
            nullable=False,
        ),
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
        sa.Column("type", postgresql.ENUM(ChannelType, name="channel_type"), nullable=False),
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
        sa.Column("min_severity", postgresql.ENUM(Severity, name="severity"), nullable=False),
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
        sa.Column("mode", postgresql.ENUM(OverrideMode, name="override_mode"), nullable=False),
        sa.Column("min_severity", postgresql.ENUM(Severity, name="severity"), nullable=True),
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
        sa.Column(
            "status", postgresql.ENUM(DeliveryStatus, name="delivery_status"), nullable=False
        ),
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

    op.execute(sa.Enum(DeliveryStatus, name="delivery_status").drop(bind=op.get_bind()))
    op.execute(sa.Enum(OverrideMode, name="override_mode").drop(bind=op.get_bind()))
    op.execute(sa.Enum(ChannelType, name="channel_type").drop(bind=op.get_bind()))
    op.execute(sa.Enum(StorageBackend, name="storage_backend").drop(bind=op.get_bind()))
    op.execute(sa.Enum(NotificationStatus, name="notification_status").drop(bind=op.get_bind()))
    op.execute(sa.Enum(SeveritySource, name="severity_source").drop(bind=op.get_bind()))
    op.execute(sa.Enum(Severity, name="severity").drop(bind=op.get_bind()))
    op.execute(sa.Enum(ReceiverStatus, name="receiver_status").drop(bind=op.get_bind()))
    op.execute(sa.Enum(UserStatus, name="user_status").drop(bind=op.get_bind()))
    op.execute(sa.Enum(UserRole, name="user_role").drop(bind=op.get_bind()))
    op.execute(sa.Enum(TenantStatus, name="tenant_status").drop(bind=op.get_bind()))

    op.execute("DROP EXTENSION IF EXISTS citext")
