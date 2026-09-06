"""Diagnose "the bot is not working".

Checks everything between your .env and Telegram, in the order things usually break,
and prints what to do about each failure.

    python scripts/doctor.py

Read-only: it never sends a message, changes a webhook, or touches the database.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import httpx

from app.config import settings

OK = "  [ OK ]"
BAD = "  [FAIL]"
WARN = "  [warn]"

problems: list[str] = []


def report(passed: bool, message: str, fix: str | None = None, *, fatal: bool = True) -> bool:
    if passed:
        print(f"{OK} {message}")
        return True
    print(f"{BAD if fatal else WARN} {message}")
    if fix:
        print(f"         -> {fix}")
        if fatal:
            problems.append(fix)
    return False


def check_env_file() -> None:
    print("\n1. Configuration")
    env = Path(".env")
    report(
        env.exists(),
        ".env exists",
        "Copy-Item .env.example .env, then set BOT_TOKEN and BOT_USERNAME",
    )
    report(
        bool(settings.bot_token) and settings.bot_token != "123456:replace-me",
        "BOT_TOKEN is set",
        "Get a token from @BotFather and put it in .env",
    )
    report(
        bool(settings.bot_username) and not settings.bot_username.startswith("@"),
        f"BOT_USERNAME = {settings.bot_username!r} (no leading @)",
        "Set BOT_USERNAME in .env to your bot username without the @",
    )


async def check_telegram() -> str | None:
    print("\n2. Telegram")
    base = f"https://api.telegram.org/bot{settings.bot_token}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            me = (await client.get(f"{base}/getMe")).json()
            if not me.get("ok"):
                report(
                    False,
                    f"getMe rejected the token: {me.get('description')}",
                    "Re-copy BOT_TOKEN from @BotFather -- it must include the digits, a colon, "
                    "and the long part",
                )
                return None

            user = me["result"]
            username = user["username"]
            print(f"{OK} token works -- @{username} (id {user['id']}, {user['first_name']})")

            report(
                username.lower() == settings.bot_username.lower(),
                f"BOT_USERNAME matches the real bot (@{username})",
                f"BOT_USERNAME in .env is {settings.bot_username!r} but the token belongs to "
                f"@{username}. Deep links are being built for the wrong bot",
            )

            hook = (await client.get(f"{base}/getWebhookInfo")).json()["result"]
            url = hook.get("url") or ""
            report(
                not url,
                "no webhook set (required for long polling)",
                f"A webhook is set to {url!r}. Long polling cannot receive updates while one "
                f"exists. Clear it: curl.exe -s "
                f"'https://api.telegram.org/bot<TOKEN>/deleteWebhook'",
            )
            pending = hook.get("pending_update_count", 0)
            if pending:
                print(f"{WARN} {pending} update(s) queued at Telegram -- nothing is consuming them")
            return username
    except httpx.HTTPError as exc:
        report(False, f"cannot reach api.telegram.org: {exc}", "Check your internet connection")
        return None


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


async def check_process() -> None:
    print("\n3. Is the bot running?")
    listening = port_in_use("127.0.0.1", settings.api_port)
    if not listening:
        report(
            False,
            f"nothing is listening on 127.0.0.1:{settings.api_port}",
            "The bot is not running. Start it in its own terminal: python -m app.main",
        )
        return

    print(f"{OK} something is listening on 127.0.0.1:{settings.api_port}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            health = await client.get(f"http://127.0.0.1:{settings.api_port}/healthz")
        report(
            health.status_code == 200 and health.json().get("status") == "ok",
            "the API answers /healthz",
            "Something else is using this port. Change API_PORT in .env",
        )
    except httpx.HTTPError:
        report(
            False,
            f"port {settings.api_port} is taken by something that is not this bot",
            "Change API_PORT in .env, or stop whatever is using the port",
        )


async def check_database() -> None:
    print("\n4. Database")
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models import BloodRequest, Donor

    if settings.database_url.startswith("sqlite"):
        path = Path(settings.database_url.split("///")[-1])
        if not path.exists():
            print(f"{WARN} {path} does not exist yet -- it is created on first start")
            return

    try:
        async with session_scope() as session:
            real = await session.scalar(
                select(func.count()).select_from(Donor).where(Donor.telegram_user_id > 0)
            )
            registered = await session.scalar(
                select(func.count())
                .select_from(Donor)
                .where(Donor.telegram_user_id > 0, Donor.is_registered.is_(True))
            )
            seeded = await session.scalar(
                select(func.count()).select_from(Donor).where(Donor.telegram_user_id < 0)
            )
            open_requests = await session.scalar(
                select(func.count()).select_from(BloodRequest).where(BloodRequest.status == "OPEN")
            )
    except Exception as exc:  # noqa: BLE001 - the point is to report, not raise
        report(False, f"cannot read the database: {exc}", "Delete blood.db and restart to rebuild")
        return

    from app.bot.storage import count as onboarding_in_flight

    print(f"{OK} database readable")
    try:
        print(f"         conversations in progress: {await onboarding_in_flight()}")
    except Exception:  # noqa: BLE001 - table may predate this build
        print(f"{WARN} fsm_state table missing -- restart the bot once to create it")
    print(f"         real donors: {real} ({registered} finished registering)")
    print(f"         seeded donors: {seeded}")
    print(f"         open requests: {open_requests}")
    if real == 0:
        print(f"{WARN} no real donors -- send /start to your bot in Telegram to register")
    elif registered == 0:
        print(f"{WARN} a donor record exists but registration was never finished")
        print("         -> send /start again and complete it through the consent step")


async def main() -> int:
    print("=" * 70)
    print("Blood Donor Bot -- diagnostics")
    print("=" * 70)

    check_env_file()
    await check_telegram()
    await check_process()
    await check_database()

    print("\n" + "=" * 70)
    if problems:
        print(f"{len(problems)} problem(s) to fix:\n")
        for i, fix in enumerate(problems, start=1):
            print(f"  {i}. {fix}")
    else:
        print("No problems found.")
        print("\nIf the bot still does not answer /start:")
        print("  - make sure `python -m app.main` is running and shows 'Run polling for bot'")
        print("  - check that terminal for a traceback after you tap something")
        print("  - only ONE process may poll a token; a second one gets a Conflict error")
    print("=" * 70)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
