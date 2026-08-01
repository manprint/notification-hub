import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine_app = create_async_engine(
    os.environ.get("DATABASE_URL_APP", "postgresql+asyncpg://user:pass@localhost/db"),
    pool_pre_ping=True,
    echo=False,
)

engine_auth = create_async_engine(
    os.environ.get("DATABASE_URL_AUTH", "postgresql+asyncpg://user:pass@localhost/db"),
    pool_pre_ping=True,
    echo=False,
)

engine_ingest = create_async_engine(
    os.environ.get("DATABASE_URL_INGEST", "postgresql+asyncpg://user:pass@localhost/db"),
    pool_pre_ping=True,
    echo=False,
)

async_session_factory_app = sessionmaker(
    engine_app,
    class_=AsyncSession,
    expire_on_commit=False,  # type: ignore[call-overload]
)

async_session_factory_auth = sessionmaker(
    engine_auth,
    class_=AsyncSession,
    expire_on_commit=False,  # type: ignore[call-overload]
)

async_session_factory_ingest = sessionmaker(
    engine_ingest,
    class_=AsyncSession,
    expire_on_commit=False,  # type: ignore[call-overload]
)


@asynccontextmanager
async def tenant_session(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    async with async_session_factory_app() as session:
        await session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def auth_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory_auth() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def ingest_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory_ingest() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
