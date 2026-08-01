"""Add groups and group_channel_bindings tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-01

"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_groups_tenant_id_name"),
    )
    op.create_index("ix_groups_tenant_id", "groups", ["tenant_id"])

    op.create_table(
        "group_channel_bindings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("min_severity", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["delivery_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "channel_id", name="uq_group_channel_bindings_group_id_channel_id"
        ),
    )
    op.create_index(
        "ix_group_channel_bindings_group_id",
        "group_channel_bindings",
        ["group_id"],
    )

    op.create_table(
        "receiver_channel_overrides",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("receiver_id", sa.UUID(), nullable=False),
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("min_severity", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receiver_id"], ["receivers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["delivery_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receiver_id", "channel_id", name="uq_receiver_channel_overrides_receiver_id_channel_id"
        ),
    )
    op.create_index(
        "ix_receiver_channel_overrides_receiver_id",
        "receiver_channel_overrides",
        ["receiver_id"],
    )

    op.add_column("receivers", sa.Column("group_id", sa.UUID(), nullable=False))
    op.create_foreign_key(
        "fk_receivers_group_id",
        "receivers",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_receivers_tenant_id_group_id", "receivers", ["tenant_id", "group_id"])


def downgrade() -> None:
    op.drop_index("ix_receivers_tenant_id_group_id", table_name="receivers")
    op.drop_constraint("fk_receivers_group_id", "receivers", type_="foreignkey")
    op.drop_column("receivers", "group_id")

    op.drop_index(
        "ix_receiver_channel_overrides_receiver_id", table_name="receiver_channel_overrides"
    )
    op.drop_table("receiver_channel_overrides")

    op.drop_index("ix_group_channel_bindings_group_id", table_name="group_channel_bindings")
    op.drop_table("group_channel_bindings")

    op.drop_index("ix_groups_tenant_id", table_name="groups")
    op.drop_table("groups")
