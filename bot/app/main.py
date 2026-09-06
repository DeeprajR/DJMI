"""Entrypoint: long-polling bot, blood-bank API and wave ticker in one event loop.

Run with ``python -m app.main``. One process is deliberate for v1 -- the pilot is a
single district and in-memory FSM state cannot be shared. Splitting the API into its own
process means moving FSM storage to Redis first.

The port is checked before anything starts, because "address already in use" is the
most common failure here and it otherwise surfaces as a page of traceback. A second
process on the same token cannot be detected up front (see ``token_is_valid``); aiogram
logs "terminated by other getUpdates request" if it happens.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import sys

import uvicorn
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

from app.api.main import create_app
from app.bot.factory import create_bot, create_dispatcher
from app.config import settings
from app.db import init_db
from app.distribution import tick

log = logging.getLogger(__name__)


def fatal(headline: str, *lines: str) -> None:
    """Print an operator-readable failure instead of a traceback."""
    print(f"\n  {headline}", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print(file=sys.stderr)


def port_is_free(host: str, port: int) -> bool:
    """Check the API port before anything starts, so failure is one line, not a stack.

    Probes the *same* address uvicorn will bind. Probing 127.0.0.1 instead would give a
    false pass on Windows, which lets a specific address bind while a wildcard bind on
    the same port is already held.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


async def token_is_valid(bot) -> bool:
    """Check the token before starting, so a bad one fails in a line rather than a stack.

    Deliberately only ``getMe``. A ``getUpdates`` probe to detect a second instance does
    not work: a short poll *succeeds* and terminates the other instance's pending long
    poll, so it causes the conflict rather than detecting it. If two processes do end up
    on one token, aiogram logs "terminated by other getUpdates request" on a retry loop
    -- that message is the signal to stop one of them.
    """
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        fatal(
            "Telegram rejected BOT_TOKEN.",
            "Re-copy it from @BotFather into .env, then run: python scripts/doctor.py",
        )
        return False
    except TelegramNetworkError as exc:
        fatal("Cannot reach Telegram.", str(exc), "Check your internet connection.")
        return False

    if me.username.lower() != settings.bot_username.lower():
        # Not fatal -- the bot works, but every forwarded deep link would be wrong.
        log.warning(
            "BOT_USERNAME is %r but the token belongs to @%s -- deep links will be broken",
            settings.bot_username,
            me.username,
        )

    log.info("token OK, polling as @%s", me.username)
    return True


async def ticker(bot) -> None:
    """Poll for due waves and expired requests.

    A database column drives escalation rather than in-memory timers, so a restart
    resumes every in-flight request instead of stranding it mid-fan-out.
    """
    while True:
        try:
            await tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("wave tick failed; continuing")
        await asyncio.sleep(settings.tick_seconds)


async def run() -> int:
    if not port_is_free(settings.api_host, settings.api_port):
        fatal(
            f"Port {settings.api_port} is already in use.",
            "Another copy of this bot is probably still running.",
            "",
            "  Find it:  Get-NetTCPConnection -LocalPort "
            f"{settings.api_port} -State Listen | Select OwningProcess",
            "  Stop it:  Get-Process python | Stop-Process -Force",
            "",
            f"Or set API_PORT in .env to a free port (currently {settings.api_port}).",
        )
        return 1

    await init_db()

    bot = create_bot()
    if not await token_is_valid(bot):
        await bot.session.close()
        return 1

    dispatcher = create_dispatcher()

    api = uvicorn.Server(
        uvicorn.Config(
            create_app(bot),
            host=settings.api_host,
            port=settings.api_port,
            log_level=settings.log_level.lower(),
        )
    )

    log.info("starting bot, API on %s:%s", settings.api_host, settings.api_port)
    tasks = [
        asyncio.create_task(dispatcher.start_polling(bot), name="bot"),
        asyncio.create_task(api.serve(), name="api"),
        asyncio.create_task(ticker(bot), name="ticker"),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        return _report(done)
    finally:
        await bot.session.close()


def _report(done: set[asyncio.Task]) -> int:
    """Turn whichever component stopped first into a useful message."""
    for task in done:
        try:
            task.result()
        except SystemExit as exc:
            # uvicorn exits this way when it cannot bind; the preflight above normally
            # catches that first, so anything reaching here is worth showing plainly.
            fatal(f"The API server stopped during startup (exit {exc.code}).")
            return 1
        except asyncio.CancelledError:
            continue
        except Exception:
            log.exception("%s stopped unexpectedly", task.get_name())
            return 1
    return 0


def main() -> int:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 0
    except SystemExit as exc:
        # uvicorn calls sys.exit() from inside its task. asyncio propagates a
        # BaseException straight out of the loop, so it never reaches _report.
        fatal(
            f"The API server could not start (exit {exc.code}).",
            f"Usually port {settings.api_port} is already taken by another instance.",
            "",
            "  Stop it:  Get-Process python | Stop-Process -Force",
            "  Diagnose: python scripts/doctor.py",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
