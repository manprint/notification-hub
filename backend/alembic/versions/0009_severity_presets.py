"""Preset di regole di severity: insiemi riusabili applicabili a piu receiver.

Tre tabelle:

- `severity_presets`         il preset (per tenant, editabile dalla dashboard)
- `severity_preset_rules`    le sue regole, stessa forma di severity_rules
- `receiver_severity_presets` quali preset sono applicati a quale receiver, e in
                              che ordine

I preset predefiniti del catalogo (app/services/severity_presets.py) NON vengono
seminati qui: una migrazione che importa codice applicativo si rompe il giorno in
cui quel codice cambia, e su un database vecchio ricostruirebbe un catalogo
diverso da quello con cui e nata. L'installazione e un'operazione esplicita:
`python -m app.cli sync-presets` (tutti i tenant) o il pulsante nella sezione
Preset. Per i tenant nuovi la fa l'applicazione al momento della creazione.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# Il tipo enum `severity` esiste gia dalla migrazione 0001: va referenziato, non
# ricreato. `sa.Enum(name=...)` generico emetterebbe comunque un CREATE TYPE.
severity_enum = postgresql.ENUM(name="severity", create_type=False)

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE IF NOT EXISTS: come in 0007, il downgrade non puo togliere un
    # valore da un enum Postgres, quindi un upgrade successivo lo ritrova.
    op.execute("ALTER TYPE severity_source ADD VALUE IF NOT EXISTS 'preset_rule' AFTER 'rule'")

    op.create_table(
        "severity_presets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("builtin_key", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_severity_presets_tenant_id_name"),
        sa.UniqueConstraint(
            "tenant_id", "builtin_key", name="uq_severity_presets_tenant_id_builtin_key"
        ),
    )

    op.create_table(
        "severity_preset_rules",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("preset_id", sa.UUID(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=200), nullable=False),
        sa.Column("case_insensitive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["preset_id"], ["severity_presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "preset_id", "priority", name="uq_severity_preset_rules_preset_id_priority"
        ),
    )
    op.create_index(
        "ix_severity_preset_rules_tenant_id_preset_id_priority",
        "severity_preset_rules",
        ["tenant_id", "preset_id", "priority"],
    )

    op.create_table(
        "receiver_severity_presets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("receiver_id", sa.UUID(), nullable=False),
        sa.Column("preset_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["receiver_id"], ["receivers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preset_id"], ["severity_presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receiver_id", "preset_id", name="uq_receiver_severity_presets_receiver_id_preset_id"
        ),
        sa.UniqueConstraint(
            "receiver_id", "position", name="uq_receiver_severity_presets_receiver_id_position"
        ),
    )
    op.create_index(
        "ix_receiver_severity_presets_tenant_id_receiver_id_position",
        "receiver_severity_presets",
        ["tenant_id", "receiver_id", "position"],
    )

    # 0004 copre i GRANT via ALTER DEFAULT PRIVILEGES; RLS va abilitata e la
    # policy creata a mano per ogni nuova tabella, come in 0003 e 0006.
    for table in ("severity_presets", "severity_preset_rules", "receiver_severity_presets"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    for table in ("receiver_severity_presets", "severity_preset_rules", "severity_presets"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_index(
        "ix_receiver_severity_presets_tenant_id_receiver_id_position",
        table_name="receiver_severity_presets",
    )
    op.drop_table("receiver_severity_presets")
    op.drop_index(
        "ix_severity_preset_rules_tenant_id_preset_id_priority", table_name="severity_preset_rules"
    )
    op.drop_table("severity_preset_rules")
    op.drop_table("severity_presets")
    # Il valore 'preset_rule' resta nel tipo enum: Postgres non sa rimuoverlo.
