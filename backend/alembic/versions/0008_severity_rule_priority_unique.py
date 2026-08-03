"""Unicita di (receiver_id, priority) sulle regole di severity.

Due regole con la stessa priorita rendevano indefinito quale delle due venisse
valutata per prima, quindi quale severity vincesse: un comportamento non
deducibile guardando la tabella in dashboard.

Le priorita esistenti vengono rinumerate 10, 20, 30... per receiver, mantenendo
l'ordine relativo attuale (priorita, poi data di creazione, poi id). L'ordine di
valutazione non cambia, cambiano i numeri.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # severity_rules ha FORCE ROW LEVEL SECURITY: la policy tenant_isolation si
    # applica anche al proprietario della tabella, e senza app.tenant_id
    # impostato questa UPDATE non vedrebbe nessuna riga. La migrazione deve
    # toccare tutti i tenant insieme, quindi il forcing viene sospeso per la
    # durata dell'operazione e ripristinato subito dopo.
    op.execute("ALTER TABLE severity_rules NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        WITH ordinate AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY receiver_id ORDER BY priority, created_at, id
                   ) * 10 AS nuova_priorita
            FROM severity_rules
        )
        UPDATE severity_rules s
        SET priority = o.nuova_priorita
        FROM ordinate o
        WHERE s.id = o.id AND s.priority <> o.nuova_priorita
        """
    )
    op.execute("ALTER TABLE severity_rules FORCE ROW LEVEL SECURITY")

    op.create_unique_constraint(
        "uq_severity_rules_receiver_id_priority", "severity_rules", ["receiver_id", "priority"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_severity_rules_receiver_id_priority", "severity_rules", type_="unique")
