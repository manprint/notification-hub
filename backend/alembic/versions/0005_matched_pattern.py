"""Notification.matched_pattern: snapshot del pattern RE2 vincente al momento
dell'ingestion, per la UI di dettaglio (spec 9.7). Denormalizzato come
content_preview: le severity_rules possono cambiare o essere cancellate dopo."""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("matched_pattern", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "matched_pattern")
