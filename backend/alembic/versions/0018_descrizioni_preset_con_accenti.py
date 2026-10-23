"""Descrizioni dei preset predefiniti con gli accenti giusti.

Il catalogo (app/services/severity_presets.py) diceva "piu" e "severita": la
correzione nel codice vale solo per le installazioni future, perche' la copia di un
preset viene fatta una volta sola (install_builtin_preset) e sovrascritta solo dal
ripristino esplicito. Questa revisione aggiorna la descrizione delle copie gia
installate, e solo dove e' ancora uguale al testo vecchio: una descrizione che
l'utente ha modificato non si tocca.

Le stringhe sono copiate qui e non importate dal catalogo: una migrazione che legge il
codice applicativo si rompe il giorno in cui il codice cambia.

severity_presets ha RLS forzata, anche per il ruolo che esegue le migrazioni: senza
app.tenant_id impostato un UPDATE non tocca nessuna riga e risulta riuscito. Quindi si
itera tenant per tenant, impostando il contesto con set_config (la tabella tenants non
ha RLS).
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_DESCRIZIONI_VECCHIE = {
    "postgres": (
        "Livelli di log del server (PANIC, FATAL, ERROR, WARNING) piu gli errori tipici di "
        "psql, pg_dump e pg_restore."
    ),
    "mongodb": (
        "Log del server (campo di severita F/E/W del formato JSON), errori di connessione e "
        "autenticazione, esiti di mongodump e mongorestore."
    ),
}

_DESCRIZIONI_NUOVE = {
    "postgres": (
        "Livelli di log del server (PANIC, FATAL, ERROR, WARNING) più gli errori tipici di "
        "psql, pg_dump e pg_restore."
    ),
    "mongodb": (
        "Log del server (campo di severità F/E/W del formato JSON), errori di connessione e "
        "autenticazione, esiti di mongodump e mongorestore."
    ),
}


def _riscrivi(da: dict[str, str], a: dict[str, str]) -> None:
    conn = op.get_bind()
    tenant_ids = conn.execute(sa.text("SELECT id FROM tenants")).scalars().all()
    for tenant_id in tenant_ids:
        conn.execute(
            sa.text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        for chiave, testo_vecchio in da.items():
            conn.execute(
                sa.text(
                    "UPDATE severity_presets SET description = :nuova "
                    "WHERE tenant_id = CAST(:tenant_id AS uuid) AND builtin_key = :chiave "
                    "AND description = :vecchia"
                ),
                {
                    "nuova": a[chiave],
                    "tenant_id": str(tenant_id),
                    "chiave": chiave,
                    "vecchia": testo_vecchio,
                },
            )


def upgrade() -> None:
    _riscrivi(da=_DESCRIZIONI_VECCHIE, a=_DESCRIZIONI_NUOVE)


def downgrade() -> None:
    # Torna al testo vecchio solo dove la descrizione e' ancora quella nuova.
    _riscrivi(da=_DESCRIZIONI_NUOVE, a=_DESCRIZIONI_VECCHIE)
