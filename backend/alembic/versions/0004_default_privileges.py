"""ALTER DEFAULT PRIVILEGES so future tables inherit the correct GRANT.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01

Migrazione 0003 concede i privilegi tabella per tabella al momento in cui esistono.
Senza questa, ogni tabella creata da una migrazione futura sfuggirebbe alle GRANT
finche qualcuno non se ne accorge (vedi docs/REVIEW.md, S2). Vale solo per le tabelle
create da notifyhub_owner, che e l'unico ruolo owner dello schema.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE notifyhub_owner IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO notifyhub_app;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE notifyhub_owner IN SCHEMA public
        REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM notifyhub_app;
        """
    )
