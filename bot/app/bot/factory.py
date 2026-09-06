"""Bot and dispatcher construction."""

from __future__ import annotations

import logging
from functools import lru_cache

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import ErrorEvent

from app.bot.middlewares import CallbackAckMiddleware, DbSessionMiddleware, DonorMiddleware
from app.bot.network import RetryOnNetworkError
from app.bot.storage import SqlAlchemyStorage
from app.config import settings

log = logging.getLogger(__name__)


def create_bot() -> Bot:
    """The bot, with outgoing calls retried on transport failures.

    ``telegram_timeout`` is generous on purpose: a slow link is better waited out than
    turned into a lost reply, and the only cost of a high ceiling is that a genuinely
    dead connection takes longer to give up on.
    """
    session = AiohttpSession(timeout=settings.telegram_timeout)
    session.middleware(
        RetryOnNetworkError(
            attempts=settings.telegram_retries,
            base_delay=settings.telegram_retry_delay,
        )
    )
    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


@lru_cache(maxsize=1)
def create_dispatcher() -> Dispatcher:
    """The process's dispatcher.

    Cached deliberately. Routers are module-level singletons (the aiogram idiom), and a
    router can only ever be attached to one dispatcher -- a second call would raise
    ``Router is already attached``. One process therefore has exactly one dispatcher,
    which is also what ``app.main`` wants.
    """
    # Imported here so the handler modules can import bot helpers without a cycle.
    from app.bot.handlers import fallback, onboarding, requests

    # Onboarding progress lives in the database, so a restart or deploy does not strand
    # a donor half-registered with the bot silently ignoring their next tap.
    dispatcher = Dispatcher(storage=SqlAlchemyStorage())

    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.middleware(DbSessionMiddleware())
        observer.middleware(DonorMiddleware())
    dispatcher.callback_query.middleware(CallbackAckMiddleware())

    dispatcher.include_router(onboarding.router)
    dispatcher.include_router(requests.router)
    dispatcher.include_router(fallback.router)  # must stay last
    dispatcher.errors.register(_on_error)
    return dispatcher


async def _on_error(event: ErrorEvent) -> bool:
    """Keep a flaky network out of the log as noise.

    A dropped connection is operational, not a defect, and its traceback is a hundred
    lines of aiohttp internals. Anything else still gets a full traceback, because that
    is a bug worth seeing.
    """
    if isinstance(event.exception, TelegramNetworkError):
        log.warning(
            "network error handling update %s: %s (the donor may need to tap again)",
            getattr(event.update, "update_id", "?"),
            event.exception.message,
        )
        return True
    log.exception(
        "unhandled error processing update %s",
        getattr(event.update, "update_id", "?"),
        exc_info=event.exception,
    )
    return True
