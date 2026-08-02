import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True, echo=False)

sync_session_factory = sessionmaker(sync_engine, class_=Session)


@contextmanager
def tenant_session_sync(tenant_id: uuid.UUID) -> Iterator[Session]:
    """Equivalente sincrono di app.db.session.tenant_session, usato dai task Celery."""
    safe_tenant_id = uuid.UUID(str(tenant_id))
    session = sync_session_factory()
    try:
        # Postgres non supporta parametri bindati su SET LOCAL: vedi app.db.session.
        session.execute(text(f"SET LOCAL app.tenant_id = '{safe_tenant_id}'"))
        yield session
    except Exception:
        session.rollback()
        raise
    else:
        # Vedi app.db.session.tenant_session: se il chiamante ha intercettato
        # un errore senza rilanciarlo, la sessione puo essere gia in stato
        # "rolled back" e commit() solleverebbe un errore indipendente.
        try:
            session.commit()
        except PendingRollbackError:
            session.rollback()
        except Exception:
            session.rollback()
            raise
    finally:
        session.close()
