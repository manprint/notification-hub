"""Add jti to refresh_tokens

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01

"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("jti", sa.String(), nullable=False, server_default=sa.func.gen_random_uuid()),
    )
    op.alter_column("refresh_tokens", "jti", server_default=None)


def downgrade() -> None:
    op.drop_column("refresh_tokens", "jti")
