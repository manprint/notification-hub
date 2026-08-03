"""user_group_memberships: associa utenti ai gruppi di receiver che gestiscono."""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_group_memberships",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "group_id", name="uq_user_group_memberships_user_id_group_id"
        ),
    )
    op.create_index(
        "ix_user_group_memberships_tenant_id_group_id",
        "user_group_memberships",
        ["tenant_id", "group_id"],
    )

    # 0004 copre solo i GRANT DML via ALTER DEFAULT PRIVILEGES: RLS va abilitata
    # e la policy creata esplicitamente per ogni nuova tabella, come in 0003.
    op.execute("ALTER TABLE user_group_memberships ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_group_memberships FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON user_group_memberships
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON user_group_memberships;")
    op.execute("ALTER TABLE user_group_memberships DISABLE ROW LEVEL SECURITY;")
    op.drop_index(
        "ix_user_group_memberships_tenant_id_group_id", table_name="user_group_memberships"
    )
    op.drop_table("user_group_memberships")
