"""Fase dell'esecuzione: distinguere "non e' partito" da "non e' finito".

La sorveglianza dell'attesa (0012) si accorge che la conclusione non e' arrivata,
ma non sa dire perche': la macchina era spenta e il job non e' mai partito, oppure
il job e' partito alle 3 ed e' morto a meta' backup insieme alla macchina. Dal
punto di vista del server i due casi sono identici, e sono guasti diversi da
cercare in posti diversi.

Il wrapper puo' quindi mandare un **ping di avvio** (`--ping-start`) prima di
eseguire il comando, con l'header `X-Phase: start`. Da quel momento:

  * `notifications.phase` registra cosa dichiarava il mittente. NULL per tutto lo
    storico e per qualunque ingestion che non lo dichiari (curl a mano).
  * `receivers.last_start_at` tiene l'ultimo avvio visto. E' separato da
    `last_notification_at`, che resta l'ultima **conclusione**: il dead man's
    switch continua a misurare gli invii che chiudono un'esecuzione, altrimenti un
    ping di avvio terrebbe la sorveglianza tranquilla proprio quando il job muore
    dopo essere partito.

Con i due istanti a disposizione, la notifica di assenza sa dire quale dei due
guasti sta segnalando.
"""

import sqlalchemy as sa

from alembic import op
from app.db.types import notification_phase_type

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    notification_phase_type.create(bind=op.get_bind(), checkfirst=True)

    op.add_column(
        "notifications",
        sa.Column("phase", sa.Enum(name="notification_phase", create_type=False), nullable=True),
    )
    op.add_column(
        "receivers", sa.Column("last_start_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("receivers", "last_start_at")
    op.drop_column("notifications", "phase")
    notification_phase_type.drop(bind=op.get_bind(), checkfirst=True)
