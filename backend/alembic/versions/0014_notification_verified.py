"""Flag di revisione manuale: l'operatore puo' contrassegnare una notifica
come verificata.

`notifications.verified` (BOOL NOT NULL DEFAULT false) e' un flag indipendente
da `status` (unread/read): segnare una notifica come verificata non cambia il
conteggio degli unread, e segnarla come letta non la rende verificata. Serve
solo a tracciare l'esito di una verifica umana, separata dalla consultazione.

Tutte le righe esistenti nascono "non verificate" grazie al server_default.
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("notifications", "verified")
