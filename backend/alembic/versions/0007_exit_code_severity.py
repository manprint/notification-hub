"""Politica di severity sull'exit code, configurabile per receiver.

L'ingestion accetta l'header `X-Exit-Code`: quando e diverso da zero e il
receiver ha una `exit_code_severity`, quella severity vince sulle regole di
contenuto (ma non su una severity esplicita). Fino a questa migrazione la
politica "exit code != 0 -> critical" viveva solo dentro lo script wrapper,
cioe cablata su ogni macchina che invia.

Il valore di partenza e `critical` per i receiver gia esistenti, cosi il
comportamento osservabile non cambia rispetto al wrapper. NULL significa
"l'exit code non influenza la severity".
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE IF NOT EXISTS: il downgrade non puo rimuovere un valore da un
    # enum Postgres, quindi un upgrade successivo lo ritroverebbe gia presente.
    op.execute("ALTER TYPE severity_source ADD VALUE IF NOT EXISTS 'exit_code' AFTER 'explicit'")

    op.add_column(
        "receivers",
        sa.Column(
            "exit_code_severity",
            sa.Enum(name="severity", create_type=False),
            nullable=True,
            server_default="critical",
        ),
    )
    # Il default lato database serve solo a valorizzare le righe esistenti: da
    # qui in avanti il valore lo decide l'applicazione, che deve poter scrivere
    # NULL per disattivare la politica.
    op.alter_column("receivers", "exit_code_severity", server_default=None)


def downgrade() -> None:
    op.drop_column("receivers", "exit_code_severity")
    # Il valore 'exit_code' resta nel tipo enum: Postgres non sa rimuoverlo.
    # Nessuna riga puo referenziarlo dopo il drop della colonna.
