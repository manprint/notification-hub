"""Slug dei receiver parlante: `gruppo-receiver-token`.

Fino a qui lo slug era il solo token casuale di 22 caratteri
(`cw2k2WWnmLalhpeyvfnCCQ`). Ora davanti ci vanno gruppo e nome del receiver
(`maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ`): una riga di crontab, un log di
nginx o un elenco di receiver diventano leggibili senza risalire all'id.

Cambia solo la LARGHEZZA della colonna, da VARCHAR(22) a VARCHAR(120):
32 caratteri per il gruppo + 32 per il receiver + i 22 del token + i separatori.
La parte casuale resta di 22 caratteri urlsafe, cioe' 128 bit: l'entropia della
credenziale di ingestion non cambia (spec 4.2, 10.2).

Gli slug esistenti NON vengono riscritti. Sono la credenziale di endpoint gia'
in produzione dentro crontab e script su macchine altrui: rinominarli in
migrazione spegnerebbe di nascosto ogni invio. Restano validi come sono e
prendono la forma nuova al primo `rotate-slug`, che e' un'azione esplicita.
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SLUG_MAX_CHARS = 120


def upgrade() -> None:
    op.alter_column(
        "receivers",
        "slug",
        existing_type=sa.String(length=22),
        type_=sa.String(length=SLUG_MAX_CHARS),
        existing_nullable=False,
    )


def downgrade() -> None:
    # VARCHAR(22) non accetta uno slug parlante, quindi la conversione riporta
    # ogni slug alla forma vecchia: gli ultimi 22 caratteri SONO il token
    # casuale, per come `build_receiver_slug` compone `gruppo-receiver-token`.
    # Il receiver resta raggiungibile a un indirizzo valido (quello che avrebbe
    # avuto prima della 0011) invece di perdere la credenziale, e uno slug gia'
    # di 22 caratteri resta identico.
    #
    # USING dentro l'ALTER e non un UPDATE a parte: `receivers` ha la RLS
    # FORCED e nessun ruolo la scavalca, quindi un UPDATE senza `app.tenant_id`
    # non vedrebbe una riga e la conversione fallirebbe comunque. Il DDL non
    # passa dalle policy.
    op.execute("ALTER TABLE receivers ALTER COLUMN slug TYPE VARCHAR(22) USING right(slug, 22)")
