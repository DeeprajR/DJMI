"""Tolerating a slow or unreliable link to Telegram.

Observed on the pilot machine: a TCP connect to api.telegram.org taking seven seconds,
TLS handshakes swinging between 0.4s and 3.8s, and intermittent
``ClientConnectorError``/``ServerDisconnectedError``. Connectivity is not broken -- every
attempt eventually succeeds -- but single calls fail often enough to matter.

aiogram retries its own ``getUpdates`` loop, but **not** the calls a handler makes. So a
failed ``message.answer`` simply lost the donor's reply: they tapped, the update was
processed, the answer never arrived, and the bot looked dead. Retrying outgoing requests
is what turns a flaky network into a slow one.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import TelegramMethod

log = logging.getLogger(__name__)


class RetryOnNetworkError(BaseRequestMiddleware):
    """Retry an outgoing Telegram call when the network, not Telegram, refuses it.

    Only transport failures are retried. An API-level rejection (bad request, blocked by
    the user) is returned untouched -- retrying those would be wrong and slow.
    """

    def __init__(self, attempts: int = 4, base_delay: float = 1.0) -> None:
        self.attempts = attempts
        self.base_delay = base_delay

    async def __call__(
        self,
        make_request: Any,
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        last: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                # Telegram's own rate limit: it tells us exactly how long to wait.
                if attempt == self.attempts:
                    raise
                log.warning("rate limited, waiting %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
                last = exc
            except TelegramNetworkError as exc:
                last = exc
                if attempt == self.attempts:
                    break
                delay = self.base_delay * (2 ** (attempt - 1))
                log.warning(
                    "%s failed (%s), retry %s/%s in %.0fs",
                    type(method).__name__,
                    exc.message,
                    attempt,
                    self.attempts - 1,
                    delay,
                )
                await asyncio.sleep(delay)

        log.error(
            "%s gave up after %s attempts: %s",
            type(method).__name__,
            self.attempts,
            last,
        )
        raise last  # type: ignore[misc]
