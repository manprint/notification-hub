"""Cascade di binding e override, indici sulle FK usate dalle cancellazioni.

1. `group_channel_bindings.group_id` e `receiver_channel_overrides.receiver_id`
   passano da NO ACTION a ON DELETE CASCADE. Prima, cancellare un gruppo con un
   canale collegato (o un receiver con un override) falliva al commit con una
   violazione di FK, dopo che il 204 era gia partito: spec 9.3, cancellazione in
   cascata. Gli override non hanno senso senza il loro receiver.

2. Indici con la colonna FK in testa per le FK ON DELETE CASCADE o NO ACTION.
   Senza, ogni DELETE di un receiver fa una sequential scan di `notifications`
   per la verifica di FK in cascata (su un milione di righe, ~60 ms contro
   ~0,1 ms con l'indice), e cancellare un gruppo ne moltiplica il costo per
   ogni receiver. Le FK verso `tenants` restano senza indice di proposito: il
   tenant si cancella solo dalla CLI, mai dall'applicazione.

   Gli indici sono creati con CREATE INDEX semplice e non CONCURRENTLY: le
   migrazioni girano in una transazione, dove CONCURRENTLY non e' ammesso. Il
   prezzo e' un lock SHARE durante la creazione, che blocca le scritture su
   quella tabella per la durata della build.

   Nota di deploy: il lock dura quanto la build su `notifications` e `deliveries`,
   cioe' il tempo di scansione della tabella. Mentre dura, l'ingestion si ferma.
   Si esegue quindi in una finestra a basso traffico. Per tabelle molto grandi, e'
   possibile creare prima gli indici con CREATE INDEX CONCURRENTLY, fuori dalla
   migrazione, e adattare la migrazione con IF NOT EXISTS.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


# (nome indice, tabella, colonna)
_FK_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_notifications_receiver_id", "notifications", "receiver_id"),
    ("ix_deliveries_channel_id", "deliveries", "channel_id"),
    ("ix_receivers_group_id", "receivers", "group_id"),
    ("ix_group_channel_bindings_channel_id", "group_channel_bindings", "channel_id"),
    ("ix_receiver_channel_overrides_channel_id", "receiver_channel_overrides", "channel_id"),
    ("ix_receiver_severity_presets_preset_id", "receiver_severity_presets", "preset_id"),
    ("ix_user_group_memberships_group_id", "user_group_memberships", "group_id"),
    ("ix_refresh_tokens_user_id", "refresh_tokens", "user_id"),
    ("ix_invitations_invited_by", "invitations", "invited_by"),
)


def upgrade() -> None:
    op.drop_constraint(
        "fk_group_channel_bindings_group_id_groups", "group_channel_bindings", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_group_channel_bindings_group_id_groups",
        "group_channel_bindings",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_receiver_channel_overrides_receiver_id_receivers",
        "receiver_channel_overrides",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_receiver_channel_overrides_receiver_id_receivers",
        "receiver_channel_overrides",
        "receivers",
        ["receiver_id"],
        ["id"],
        ondelete="CASCADE",
    )

    for name, table, column in _FK_INDEXES:
        op.create_index(name, table, [column])


def downgrade() -> None:
    for name, table, _column in _FK_INDEXES:
        op.drop_index(name, table_name=table)

    op.drop_constraint(
        "fk_receiver_channel_overrides_receiver_id_receivers",
        "receiver_channel_overrides",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_receiver_channel_overrides_receiver_id_receivers",
        "receiver_channel_overrides",
        "receivers",
        ["receiver_id"],
        ["id"],
    )
    op.drop_constraint(
        "fk_group_channel_bindings_group_id_groups", "group_channel_bindings", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_group_channel_bindings_group_id_groups",
        "group_channel_bindings",
        "groups",
        ["group_id"],
        ["id"],
    )
