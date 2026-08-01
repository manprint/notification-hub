"""Add pending_object_deletions table

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-01

"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_object_deletions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pending_object_deletions")
