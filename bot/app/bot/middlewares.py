"""Dispatcher middlewares: one transaction per update, and the donor row alongside it."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject, User

from app.db import current_session, session_scope
from app.models import Donor

log = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Give each update its own transaction.

    Committing per update is what makes duplicate callback taps safe: the second tap
    sees the first one's committed status and its conditional UPDATE matches nothing.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with session_scope() as session:
            token = current_session.set(session)
            try:
                data["session"] = session
                return await handler(event, data)
            finally:
                current_session.reset(token)


class DonorMiddleware(BaseMiddleware):
    """Attach the donor record (or None for a brand-new user) to every handler."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        session = data["session"]
        donor: Donor | None = None
        if user is not None:
            donor = await session.get(Donor, user.id)
        data["donor"] = donor
        return await handler(event, data)


class CallbackAckMiddleware(BaseMiddleware):
    """Answer every callback query so the donor never sees a spinning button.

    Handlers may answer first with their own text; a second answer is a harmless no-op.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        finally:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:  # noqa: BLE001 - the query may already be answered/expired
                    pass
