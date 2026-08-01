"""Add archived_at to notifications

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-01

"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_archived_at",
        "notifications",
        ["archived_at"],
        postgresql_where="archived_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_archived_at", table_name="notifications")
    op.drop_column("notifications", "archived_at")
