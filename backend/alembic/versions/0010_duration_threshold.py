"""Soglia di durata dell'esecuzione, configurabile per receiver.

Il wrapper `notifyhub-run.sh` misura quanto e' durato il comando e lo manda
nell'header `X-Duration-Ms`. Quando la durata supera
`receivers.duration_threshold_seconds`, la notifica prende
`receivers.duration_severity`: un backup che di solito finisce in 5 minuti e
oggi ne ha impiegati 20 finisce sul canale di allarme anche se e' terminato con
exit code 0, cioe' senza che niente nel suo output dica che qualcosa non va.

Le due colonne vivono insieme: una soglia senza severity non saprebbe cosa fare
e una severity senza soglia non scatterebbe mai, quindi il CHECK impone
entrambe-o-nessuna. NULL/NULL (il default per i receiver esistenti) significa
"la durata non influenza la severity", come NULL su exit_code_severity.

Su `notifications` vengono aggiunte due colonne di dato grezzo:

  * `duration_ms`: serve alla dashboard (mostrare la durata, filtrare i job
    lenti) e al replay, che senza il dato non potrebbe rivalutare la soglia.
  * `exit_code`: fino a qui l'exit code veniva usato per decidere la severity e
    poi buttato via, sopravvivendo solo come testo dentro il corpo. Con la
    colonna il replay diventa fedele anche per il passo dell'exit code.

Entrambe NULL per tutto lo storico: nessuna notifica gia' arrivata ha il dato.
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE IF NOT EXISTS: un enum Postgres non sa perdere un valore, quindi
    # dopo un downgrade il valore resta e questo upgrade lo ritrova (vedi 0007).
    op.execute("ALTER TYPE severity_source ADD VALUE IF NOT EXISTS 'duration' AFTER 'exit_code'")

    op.add_column(
        "receivers",
        sa.Column("duration_threshold_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "receivers",
        sa.Column(
            "duration_severity",
            sa.Enum(name="severity", create_type=False),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_receivers_duration_policy",
        "receivers",
        "(duration_threshold_seconds IS NULL AND duration_severity IS NULL) "
        "OR (duration_threshold_seconds IS NOT NULL AND duration_severity IS NOT NULL "
        "AND duration_threshold_seconds > 0)",
    )

    op.add_column("notifications", sa.Column("duration_ms", sa.BigInteger(), nullable=True))
    op.add_column("notifications", sa.Column("exit_code", sa.Integer(), nullable=True))
    # Una durata negativa non esiste: l'header viene filtrato in ingestion,
    # il vincolo protegge da scritture fatte per altre strade.
    op.create_check_constraint(
        "ck_notifications_duration_ms",
        "notifications",
        "duration_ms IS NULL OR duration_ms >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_notifications_duration_ms", "notifications", type_="check")
    op.drop_column("notifications", "exit_code")
    op.drop_column("notifications", "duration_ms")
    op.drop_constraint("ck_receivers_duration_policy", "receivers", type_="check")
    op.drop_column("receivers", "duration_severity")
    op.drop_column("receivers", "duration_threshold_seconds")
    # Il valore 'duration' resta nel tipo enum severity_source: Postgres non sa
    # rimuoverlo. Nessuna riga puo' referenziarlo dopo il drop delle colonne.
