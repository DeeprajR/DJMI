"""Whitelist a volunteer admin (PRD open question: manual for v1).

Admins receive every new request as a card with a live counter plus a message to
forward. Scope one to a district, or leave the district off to receive everything.

    python scripts/add_admin.py 404413376 --name "Deepraj" --district Kozhikode
    python scripts/add_admin.py 404413376 --deactivate
    python scripts/add_admin.py --list

The Telegram id is the number shown by `scripts/inspect_db.py` once the person has
sent /start to the bot, or from @userinfobot.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db import init_db, session_scope
from app.i18n import tl
from app.models import Admin


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("telegram_id", type=int, nargs="?")
    parser.add_argument("--name", default=None)
    parser.add_argument("--district", default=None, help="omit to cover every district")
    parser.add_argument("--deactivate", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    await init_db()

    if args.list:
        async with session_scope() as session:
            rows = list(await session.scalars(select(Admin).order_by(Admin.telegram_user_id)))
        if not rows:
            print("No admins yet.")
        for a in rows:
            state = "active" if a.active else "inactive"
            scope = a.district or "all districts"
            print(f"  {a.telegram_user_id:>12}  {(a.name or '-'):<20} {scope:<18} {state}")
        return 0

    if args.telegram_id is None:
        parser.error("telegram_id is required unless --list")

    if args.district and args.district not in tl("regions.districts"):
        print(f"Unknown district {args.district!r}. Known: {', '.join(tl('regions.districts'))}")
        return 1

    async with session_scope() as session:
        admin = await session.get(Admin, args.telegram_id)
        if admin is None:
            admin = Admin(telegram_user_id=args.telegram_id)
            session.add(admin)
        if args.name:
            admin.name = args.name
        if args.district is not None:
            admin.district = args.district
        admin.active = not args.deactivate

    verb = "Deactivated" if args.deactivate else "Whitelisted"
    scope = args.district or "all districts"
    print(f"{verb} admin {args.telegram_id} ({args.name or 'unnamed'}, {scope}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
