"""Provision the one PostgreSQL database that Modules 1, 2 and 3 share.

    python scripts/setup_shared_db.py postgresql://postgres:<password>@127.0.0.1:5432

Creates the `blood_request` database if it is missing, creates the bot's `donor_bot`
schema and tables, and prints the exact lines to put in each module's .env. Running
the hospital app's migrations (`npm run db:migrate`) is a separate step, printed at
the end, because that repo owns those tables.

Safe to re-run: every step is idempotent.
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlsplit, urlunsplit

import asyncpg

DB_NAME = "blood_request"
BOT_SCHEMA = "donor_bot"


def with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


async def main(server_url: str) -> int:
    admin_url = with_database(server_url, "postgres")
    try:
        conn = await asyncpg.connect(admin_url.replace("postgresql+asyncpg://", "postgresql://"))
    except Exception as exc:  # noqa: BLE001 - report plainly
        print(f"Cannot connect: {type(exc).__name__}: {exc}")
        return 1

    try:
        version = await conn.fetchval("select version()")
        print(f"Connected: {version.split(',')[0]}")
        exists = await conn.fetchval("select 1 from pg_database where datname = $1", DB_NAME)
        if exists:
            print(f"Database {DB_NAME!r} already exists.")
        else:
            await conn.execute(f'create database "{DB_NAME}"')
            print(f"Created database {DB_NAME!r}.")
    finally:
        await conn.close()

    app_url = with_database(server_url, DB_NAME).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(app_url)
    try:
        await conn.execute(f'create schema if not exists "{BOT_SCHEMA}"')
        print(f"Schema {BOT_SCHEMA!r} ready.")
    finally:
        await conn.close()

    bot_url = app_url.replace("postgresql://", "postgresql+asyncpg://")
    print(
        "\nPut this in the BOT's .env (bloody-project/.env):\n"
        f"  DATABASE_URL={bot_url}\n"
        f"  DB_SCHEMA={BOT_SCHEMA}\n"
        "  BANK_SYNC_ENABLED=true\n"
        "\nPut this in the HOSPITAL app's .env (the repo root .env):\n"
        f"  DATABASE_URL={app_url}\n"
        "\nThen, from the repo root:\n"
        "  npm run db:migrate          # Modules 1 + 2 tables\n"
        "  npm run seed:admin          # first admin account\n"
        "  npm run seed:bank -- --email bank@example.com --password <12+ chars> "
        "--name 'Blood Bank'\n"
        "\nAnd from bloody-project:\n"
        "  python -m app.main          # creates the donor_bot tables on first start\n"
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
