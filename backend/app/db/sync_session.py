import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

sync_engine = create_engine(
    os.environ.get("DATABASE_URL_SYNC", "postgresql+psycopg://user:pass@localhost/db"),
    pool_pre_ping=True,
    echo=False,
)

sync_session_factory = sessionmaker(sync_engine, class_=Session)


@contextmanager
def tenant_session_sync(tenant_id: uuid.UUID) -> Iterator[Session]:
    session = sync_session_factory()
    try:
        session.execute(text(f"SET LOCAL app.tenant_id = '{str(tenant_id)}'"))
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
