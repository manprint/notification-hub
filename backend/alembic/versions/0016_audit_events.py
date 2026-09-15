"""Audit: registro di chi ha fatto cosa (spec 9.6).

Tre cose in una sola migrazione perche' sono un solo fatto:

1. `audit_events`, tenant-scoped sotto RLS forzata come ogni altra tabella di
   tenant, con `REVOKE UPDATE` per il ruolo dell'applicazione: la tabella e'
   append-only per NotifyHub. Il `DELETE` resta, perche' la purge notturna di
   ritenzione gira con lo stesso ruolo `notifyhub_app` e un quarto ruolo solo
   per lei costerebbe piu' di quanto valga.
2. `tenants.audit_retention_days` (default 365): l'audit deve sopravvivere alle
   notifiche che descrive, la cui ritenzione di default e' 90 giorni.
3. `notifications.read_by/read_at/verified_by/verified_at`: chi ha gestito la
   notifica, leggibile da chiunque veda la notifica. Lo storico completo dei
   passaggi (compresi i ripristini) resta in `audit_events`, riservato a owner
   e admin.

L'indice GIN su `context->'notification_ids'` esiste per il bulk-read, che
tocca N notifiche con un solo evento: senza di lui, filtrare l'audit per una
singola notifica non troverebbe mai le letture di massa se non con un
sequential scan.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    audit_outcome = postgresql.ENUM("success", "failure", name="audit_outcome")
    audit_outcome.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column(
            "actor_role",
            postgresql.ENUM(name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("resource_label", sa.String(length=255), nullable=True),
        sa.Column(
            "outcome",
            postgresql.ENUM(name="audit_outcome", create_type=False),
            nullable=False,
        ),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_audit_events_tenant_id_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )

    op.create_index(
        "ix_audit_events_tenant_id_occurred_at_id",
        "audit_events",
        ["tenant_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_audit_events_tenant_id_resource_type_resource_id_occurred_at",
        "audit_events",
        ["tenant_id", "resource_type", "resource_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_tenant_id_actor_user_id_occurred_at",
        "audit_events",
        ["tenant_id", "actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_tenant_id_action_occurred_at",
        "audit_events",
        ["tenant_id", "action", "occurred_at"],
    )
    op.execute(
        """
        CREATE INDEX ix_audit_events_context_notification_ids
        ON audit_events USING gin ((context -> 'notification_ids') jsonb_path_ops);
        """
    )

    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON audit_events
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
        """
    )
    # La GRANT arriva da ALTER DEFAULT PRIVILEGES (migrazione 0004): qui si
    # toglie solo cio' che l'audit non deve concedere. Un evento scritto non si
    # corregge.
    op.execute("REVOKE UPDATE ON audit_events FROM notifyhub_app;")

    op.add_column(
        "tenants",
        sa.Column("audit_retention_days", sa.Integer(), nullable=True, server_default="365"),
    )

    for column in ("read_by", "verified_by"):
        op.add_column("notifications", sa.Column(column, sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_notifications_{column}_users",
            "notifications",
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )
    for column in ("read_at", "verified_at"):
        op.add_column("notifications", sa.Column(column, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ("read_at", "verified_at"):
        op.drop_column("notifications", column)
    for column in ("read_by", "verified_by"):
        op.drop_constraint(f"fk_notifications_{column}_users", "notifications", type_="foreignkey")
        op.drop_column("notifications", column)

    op.drop_column("tenants", "audit_retention_days")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_events;")
    op.drop_table("audit_events")
    postgresql.ENUM(name="audit_outcome").drop(op.get_bind(), checkfirst=True)
