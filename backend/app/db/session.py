import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine_app = create_async_engine(settings.database_url_app, pool_pre_ping=True, echo=False)
engine_auth = create_async_engine(settings.database_url_auth, pool_pre_ping=True, echo=False)
engine_ingest = create_async_engine(settings.database_url_ingest, pool_pre_ping=True, echo=False)

async_session_factory_app = async_sessionmaker(engine_app, expire_on_commit=False)
async_session_factory_auth = async_sessionmaker(engine_auth, expire_on_commit=False)
async_session_factory_ingest = async_sessionmaker(engine_ingest, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Sessione sul pool notifyhub_app con app.tenant_id impostato per la transazione.

    Il chiamante non deve mai invocare session.commit(): SET LOCAL vale solo fino al
    commit della transazione corrente, quindi il commit appartiene esclusivamente a
    questo context manager (spec 5.3, invariante I-1).
    """
    # uuid.UUID(...) rivalida il valore anche se il chiamante non ha rispettato il
    # type hint: nessuna stringa arbitraria puo raggiungere l'interpolazione sotto.
    safe_tenant_id = uuid.UUID(str(tenant_id))

    async with async_session_factory_app() as session:
        # Postgres non supporta parametri bindati su SET: "SET LOCAL x = $1" e un
        # errore di sintassi. L'interpolazione qui e sicura perche safe_tenant_id e
        # sempre un uuid.UUID, la cui rappresentazione in stringa e sempre nel
        # formato canonico 8-4-4-4-12 esadecimale, senza apici ne caratteri di fuga.
        await session.execute(text(f"SET LOCAL app.tenant_id = '{safe_tenant_id}'"))
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            # Se il chiamante ha intercettato un errore avvenuto durante lo
            # `yield` senza rilanciarlo (per esempio un test con pytest.raises,
            # o una validazione applicativa che converte l'eccezione in un
            # Problem), la sessione puo essere gia in stato "rolled back" per
            # via del flush fallito. L'errore originale e gia stato consegnato
            # e gestito dal chiamante: qui basta chiudere pulito con un
            # rollback, senza sollevare un secondo errore che non aggiunge
            # informazione. Un fallimento del commit per qualunque ALTRA
            # ragione resta invece un problema reale e va propagato.
            try:
                await session.commit()
            except PendingRollbackError:
                await session.rollback()
            except Exception:
                await session.rollback()
                raise


@asynccontextmanager
async def auth_session() -> AsyncIterator[AsyncSession]:
    """Sessione di sola lettura sul pool notifyhub_auth, senza contesto di tenant."""
    async with async_session_factory_auth() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def ingest_session() -> AsyncIterator[AsyncSession]:
    """Sessione di sola lettura sul pool notifyhub_ingest, per risolvere lo slug."""
    async with async_session_factory_ingest() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
