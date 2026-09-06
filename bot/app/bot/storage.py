"""Database-backed FSM storage.

aiogram's default ``MemoryStorage`` keeps half-finished onboarding in a dict, so every
restart or crash silently drops it: the donor taps "Share my number", no handler matches
the now-stateless update, and the bot answers nothing at all. During a pilot -- where the
process gets restarted for every deploy -- that reads as "the bot is broken".

Storing state in the same database as everything else fixes that, and is a prerequisite
for running more than one process later (PRD 12 notes the Redis alternative; this needs
no extra infrastructure for a single-district pilot).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from sqlalchemy import delete, select

from app.db import current_session, session_scope
from app.models import FSMRecord


def _key(key: StorageKey) -> str:
    """Flatten a StorageKey. Business/thread ids are included so nothing collides."""
    parts = [
        str(key.bot_id),
        str(key.chat_id),
        str(key.user_id),
        str(key.thread_id or ""),
        str(key.business_connection_id or ""),
        str(key.destiny),
    ]
    return ":".join(parts)


@asynccontextmanager
async def _session() -> AsyncIterator:
    """The handler's session when inside one, otherwise a short transaction of our own.

    Joining the handler's transaction does two things. It removes the deadlock: the
    consent step inserts the donor row and then clears state, and with a second SQLite
    connection that second write waited on the first until the busy timeout expired.
    And it makes state changes atomic with the handler's writes -- if the reply to the
    donor fails and the handler rolls back, the state rolls back with it, so the donor's
    next tap lands where they actually are.

    Outside a handler (aiogram evaluating a state filter, tests, maintenance) there is
    no shared session, and a private one is used.
    """
    shared = current_session.get()
    if shared is not None:
        yield shared
        await shared.flush()
        return
    async with session_scope() as session:
        yield session


class SqlAlchemyStorage(BaseStorage):
    """FSM state persisted in the ``fsm_state`` table."""

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with _session() as session:
            record = await session.get(FSMRecord, _key(key))
            if value is None:
                # No state and no data left means the row has nothing to say.
                if record is not None:
                    if record.data:
                        record.state = None
                    else:
                        await session.delete(record)
                return
            if record is None:
                session.add(FSMRecord(key=_key(key), state=value, data={}))
            else:
                record.state = value

    async def get_state(self, key: StorageKey) -> str | None:
        async with _session() as session:
            record = await session.get(FSMRecord, _key(key))
            return record.state if record else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        payload = dict(data)
        async with _session() as session:
            record = await session.get(FSMRecord, _key(key))
            if record is None:
                if payload:
                    session.add(FSMRecord(key=_key(key), state=None, data=payload))
                return
            if not payload and record.state is None:
                await session.delete(record)
                return
            record.data = payload

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with _session() as session:
            record = await session.get(FSMRecord, _key(key))
            return dict(record.data) if record and record.data else {}

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        async with _session() as session:
            record = await session.get(FSMRecord, _key(key))
            merged = dict(record.data) if record and record.data else {}
            merged.update(data)
            if record is None:
                session.add(FSMRecord(key=_key(key), state=None, data=merged))
            else:
                # Reassigned rather than mutated so SQLAlchemy sees the JSON change.
                record.data = merged
            return merged

    async def close(self) -> None:
        return None


async def clear_all() -> None:
    """Drop every stored conversation. Test and maintenance helper."""
    async with session_scope() as session:
        await session.execute(delete(FSMRecord))


async def count() -> int:
    async with session_scope() as session:
        rows = await session.scalars(select(FSMRecord.key))
        return len(list(rows))
