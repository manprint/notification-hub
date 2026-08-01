"""Add full-text search index to notifications

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-01

"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_notifications_content_preview_fts
        ON notifications
        USING GIN(to_tsvector('english', content_preview))
        WHERE archived_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_content_preview_fts", table_name="notifications")
