"""Surviving a slow or intermittent link to Telegram.

aiogram retries its own polling loop but not the calls a handler makes, so before this a
single dropped connection lost the donor's reply outright: the update was processed, the
answer never sent, and the bot looked dead.
"""

from __future__ import annotations

import asyncio

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage

from app.bot.network import RetryOnNetworkError


def send() -> SendMessage:
    return SendMessage(chat_id=1, text="hello")


def network_error() -> TelegramNetworkError:
    return TelegramNetworkError(method=send(), message="ClientConnectorError: cannot connect")


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Backoff is real in production; here it would only slow the suite down."""
    real_sleep = asyncio.sleep

    async def instant(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", instant)


async def test_a_flaky_send_succeeds_on_retry():
    calls = {"n": 0}

    async def make_request(bot, method):
        calls["n"] += 1
        if calls["n"] < 3:
            raise network_error()
        return "sent"

    middleware = RetryOnNetworkError(attempts=4, base_delay=0)
    assert await middleware(make_request, bot=None, method=send()) == "sent"
    assert calls["n"] == 3


async def test_a_working_link_is_not_retried():
    calls = {"n": 0}

    async def make_request(bot, method):
        calls["n"] += 1
        return "sent"

    middleware = RetryOnNetworkError(attempts=4, base_delay=0)
    await middleware(make_request, bot=None, method=send())
    assert calls["n"] == 1


async def test_it_gives_up_and_reports_the_last_failure():
    async def make_request(bot, method):
        raise network_error()

    middleware = RetryOnNetworkError(attempts=3, base_delay=0)
    with pytest.raises(TelegramNetworkError):
        await middleware(make_request, bot=None, method=send())


async def test_it_stops_at_the_configured_attempt_count():
    calls = {"n": 0}

    async def make_request(bot, method):
        calls["n"] += 1
        raise network_error()

    middleware = RetryOnNetworkError(attempts=3, base_delay=0)
    with pytest.raises(TelegramNetworkError):
        await middleware(make_request, bot=None, method=send())
    assert calls["n"] == 3


async def test_an_api_rejection_is_never_retried():
    """A bad request is Telegram answering, not the network failing. Retrying is wrong."""
    calls = {"n": 0}

    async def make_request(bot, method):
        calls["n"] += 1
        raise ValueError("chat not found")

    middleware = RetryOnNetworkError(attempts=4, base_delay=0)
    with pytest.raises(ValueError):
        await middleware(make_request, bot=None, method=send())
    assert calls["n"] == 1, "an API-level error must not be retried"


async def test_rate_limiting_waits_and_retries():
    calls = {"n": 0}

    async def make_request(bot, method):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TelegramRetryAfter(method=send(), message="Too Many Requests", retry_after=1)
        return "sent"

    middleware = RetryOnNetworkError(attempts=4, base_delay=0)
    assert await middleware(make_request, bot=None, method=send()) == "sent"
    assert calls["n"] == 2


async def test_backoff_grows_between_attempts(monkeypatch):
    delays: list[float] = []

    async def record(seconds):
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", record)

    async def make_request(bot, method):
        raise network_error()

    middleware = RetryOnNetworkError(attempts=4, base_delay=1.0)
    with pytest.raises(TelegramNetworkError):
        await middleware(make_request, bot=None, method=send())

    assert delays == [1.0, 2.0, 4.0], "delays should double, not hammer a struggling link"
