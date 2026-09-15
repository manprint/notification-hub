"""Ricerca sull'intero contenuto del messaggio, non piu' sui primi 4096 caratteri.

Fino alla 0014 il filtro `q` girava su `content_preview`, cioe' sui primi 4096
caratteri: un messaggio lungo era cercabile solo per la sua testa. La ricerca
passa ora su `COALESCE(content, content_preview)`:

- payload inline (<= notifyhub_inline_max_bytes, default 1MB): `content` e' il
  corpo intero, quindi la ricerca lo copre tutto;
- payload offloaded su object storage: `content` e' NULL per vincolo
  (ck_notifications_body) e il corpo vive su MinIO, irraggiungibile da Postgres.
  Il COALESCE fa ricadere quelle righe su `content_preview`, cioe' sul
  comportamento di prima: e' il massimo che il database puo' garantire senza
  duplicare in tabella fino a 20MB per notifica.

Cambia anche la semantica del match: da `plainto_tsquery` (parole intere, `err`
non trovava `error`) a ILIKE su sottostringa, che e' quello che ci si aspetta da
una casella "cerca nel contenuto" applicata a dei log. L'indice GIN sul tsvector
diventa quindi inutile e viene sostituito da un GIN pg_trgm sulla stessa
espressione usata dalla query, unica forma che il planner sa riconoscere.

pg_trgm e' un'estensione trusted da PostgreSQL 13: notifyhub_owner, proprietario
del database, puo' crearla senza essere superuser (stessa strada di citext nella
0001).
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_TRGM_INDEX = "ix_notifications_content_trgm"
_TSVECTOR_INDEX = "ix_notifications_content_preview_tsvector"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # IF EXISTS: l'indice nasce nella 0002, ma un'installazione che avesse gia'
    # applicato a mano la sostituzione non deve far fallire l'aggiornamento.
    op.execute(f"DROP INDEX IF EXISTS {_TSVECTOR_INDEX}")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_TRGM_INDEX} ON notifications "
        "USING gin ((COALESCE(content, content_preview)) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_TRGM_INDEX}")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_TSVECTOR_INDEX} ON notifications "
        "USING gin (to_tsvector('simple', content_preview))"
    )
    # pg_trgm resta installata: e' condivisa col database e rimuoverla
    # romperebbe qualunque altro oggetto che ci si appoggia.
