"""Async SQLAlchemy engine / session plumbing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

#: The session of the update currently being handled, if any. Set by the dispatcher
#: middleware so that FSM storage joins the handler's transaction instead of opening a
#: second connection -- on SQLite a second connection deadlocks against the first the
#: moment the handler has written anything.
current_session: ContextVar[AsyncSession | None] = ContextVar("current_session", default=None)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:
        """Make SQLite behave under concurrent handlers.

        A handler holds its transaction open while it talks to Telegram, and on a slow
        link that can be tens of seconds. In the default rollback-journal mode that
        blocks every other reader and writer, and they fail after five seconds with
        "database is locked". WAL lets readers proceed regardless, and the busy timeout
        makes a competing writer wait rather than fail.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session. Commits on clean exit, rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create the bot's schema and tables. v1 ships without migrations; add Alembic
    before the pilot widens."""
    from app.models import Base

    async with engine.begin() as conn:
        if settings.db_schema and engine.dialect.name == "postgresql":
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
        await conn.run_sync(Base.metadata.create_all)
