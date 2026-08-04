"""Sorveglianza dell'attesa: accorgersi che una notifica NON e' arrivata.

Tutta la catena di severity ragiona su notifiche che arrivano. Il guasto piu'
banale invece non ne produce nessuna: la macchina e' spenta, cron e' disabilitato,
la rete verso NotifyHub non c'e'. Nessuno parla, e proprio per questo nessuno se
ne accorge.

Il rimedio e' un dead man's switch lato server: sul receiver si dichiara ogni
quanto ci si aspetta un invio, e un job di Celery beat controlla ogni minuto chi
ha sforato. Chi sfora produce una notifica sintetica con
`receivers.missing_severity`, che passa dallo stesso instradamento per severity
delle notifiche vere: nessun percorso di consegna nuovo.

Due modi di dichiarare l'attesa, uno solo per receiver:

  * `expected_every_seconds`: intervallo fisso ("ogni 24 ore"). Semplice, copre
    i job periodici equispaziati.
  * `expected_cron` + `expected_timezone`: la stessa espressione che sta nel
    crontab ("0 3 * * 1-5"). Serve ai job non equispaziati, che con un intervallo
    fisso darebbero falsi allarmi ogni fine settimana.

`expected_grace_seconds` e' la tolleranza (jitter di cron, durata del job) e
`missing_severity` la severity dell'assenza: attive insieme o tutte NULL, come la
coppia della soglia di durata.

Lo stato della sorveglianza sta su tre colonne:

  * `last_notification_at`: denormalizzata dall'ingestion, cosi' il job fa una
    query indicizzata sui receiver invece di un max() su `notifications`.
  * `expected_since`: da quando la politica e' in vigore. Serve al receiver che
    non ha mai ricevuto niente: si conta da qui, non dall'inizio dei tempi.
  * `missing_alerted_at`: assenza gia' segnalata. Una notifica per assenza, non
    una al minuto; si riarma al primo invio vero.
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Due nuove origini della severity: l'assenza e il rientro. Come per
    # 'duration' (0010), IF NOT EXISTS perche' un enum Postgres non sa perdere
    # valori e dopo un downgrade li ritroverebbe.
    op.execute("ALTER TYPE severity_source ADD VALUE IF NOT EXISTS 'missing' AFTER 'duration'")
    op.execute("ALTER TYPE severity_source ADD VALUE IF NOT EXISTS 'recovered' AFTER 'missing'")

    op.add_column("receivers", sa.Column("expected_every_seconds", sa.Integer(), nullable=True))
    op.add_column("receivers", sa.Column("expected_cron", sa.String(length=100), nullable=True))
    op.add_column("receivers", sa.Column("expected_timezone", sa.String(length=64), nullable=True))
    op.add_column("receivers", sa.Column("expected_grace_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "receivers",
        sa.Column("missing_severity", sa.Enum(name="severity", create_type=False), nullable=True),
    )
    op.add_column(
        "receivers", sa.Column("expected_since", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "receivers", sa.Column("last_notification_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "receivers", sa.Column("missing_alerted_at", sa.DateTime(timezone=True), nullable=True)
    )

    # La politica e' spenta (tutto NULL) oppure completa: esattamente uno fra
    # intervallo ed espressione cron, piu' tolleranza e severity. Il fuso ha
    # senso solo col cron. L'API rifiuta gli stati intermedi con 422; il vincolo
    # tiene fuori dal database quello che passasse per altre strade.
    op.create_check_constraint(
        "ck_receivers_expected_policy",
        "receivers",
        """
        (
            expected_every_seconds IS NULL AND expected_cron IS NULL
            AND expected_grace_seconds IS NULL AND missing_severity IS NULL
            AND expected_timezone IS NULL
        )
        OR (
            (
                (expected_every_seconds IS NOT NULL AND expected_cron IS NULL
                 AND expected_every_seconds > 0)
                OR (expected_every_seconds IS NULL AND expected_cron IS NOT NULL)
            )
            AND expected_grace_seconds IS NOT NULL AND expected_grace_seconds >= 0
            AND missing_severity IS NOT NULL
            AND (expected_timezone IS NULL OR expected_cron IS NOT NULL)
        )
        """,
    )

    # Il job gira ogni minuto e cerca solo i receiver sorvegliati: indice
    # parziale, che su un'istanza dove nessuno usa la sorveglianza non costa
    # niente e non cresce.
    op.execute(
        "CREATE INDEX ix_receivers_expected_active ON receivers (tenant_id) "
        "WHERE missing_severity IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_receivers_expected_active")
    op.drop_constraint("ck_receivers_expected_policy", "receivers", type_="check")
    for column in (
        "missing_alerted_at",
        "last_notification_at",
        "expected_since",
        "missing_severity",
        "expected_grace_seconds",
        "expected_timezone",
        "expected_cron",
        "expected_every_seconds",
    ):
        op.drop_column("receivers", column)
    # I valori 'missing' e 'recovered' restano nel tipo severity_source: Postgres
    # non sa rimuoverli. Le notifiche che li usano vengono da questa feature,
    # quindi dopo il downgrade non ne nascono altre.
