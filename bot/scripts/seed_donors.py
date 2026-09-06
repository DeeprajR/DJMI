"""Seed a synthetic donor pool so wave behaviour is visible in local testing.

Seeded donors carry negative Telegram ids. Real ids are always positive, so a seeded
record can never collide with a real one and is trivially safe to delete:

    python scripts/seed_donors.py --count 60 --district Ernakulam
    python scripts/seed_donors.py --clear

They cannot receive messages -- delivery to a fake id fails and the wave simply skips
them. Use them to exercise eligibility and ordering, and register yourself for the
message flow.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select

from app.db import init_db, session_scope
from app.enums import REAL_GROUPS, Sex
from app.i18n import tl
from app.models import Donor

SEED_ID_FLOOR = -1_000_000


async def clear() -> int:
    async with session_scope() as session:
        result = await session.execute(delete(Donor).where(Donor.telegram_user_id < 0))
        return result.rowcount


async def seed(count: int, district: str, seed_value: int) -> tuple[int, int]:
    rng = random.Random(seed_value)
    towns = tl(f"regions.cities.{district}") or [district]

    async with session_scope() as session:
        lowest = await session.scalar(
            select(Donor.telegram_user_id).order_by(Donor.telegram_user_id)
        )
        next_id = min(lowest or SEED_ID_FLOOR, SEED_ID_FLOOR) - 1

        for i in range(count):
            age = rng.randint(18, 65)
            sex = rng.choice([Sex.MALE, Sex.MALE, Sex.FEMALE])
            # A third have never donated, the rest last donated 10-500 days ago -- enough
            # spread that the cooldown rule and the wave ordering both show up.
            last = (
                None if rng.random() < 0.33 else date.today() - timedelta(days=rng.randint(10, 500))
            )
            session.add(
                Donor(
                    telegram_user_id=next_id - i,
                    phone=f"+9199{abs(next_id - i):09d}"[:15],
                    full_name=f"Seed Donor {i + 1}",
                    dob=date.today().replace(year=date.today().year - age),
                    sex=sex,
                    blood_group=rng.choice(REAL_GROUPS).value,
                    district=district,
                    city=rng.choice(towns),
                    last_donation_date=last,
                    is_registered=True,
                    consent_at=datetime.now(UTC),
                )
            )

        await session.flush()
        total = len((await session.scalars(select(Donor).where(Donor.telegram_user_id < 0))).all())
        return count, total


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--district", default="Ernakulam")
    parser.add_argument("--seed", type=int, default=1, help="fixed for reproducible pools")
    parser.add_argument("--clear", action="store_true", help="delete all seeded donors and exit")
    args = parser.parse_args()

    await init_db()

    if args.clear:
        removed = await clear()
        print(f"Removed {removed} seeded donors.")
        return

    districts = tl("regions.districts")
    if args.district not in districts:
        print(f"Unknown district {args.district!r}. Known: {', '.join(districts)}")
        return

    added, total = await seed(args.count, args.district, args.seed)
    print(f"Added {added} seeded donors in {args.district} ({total} seeded donors in total).")


if __name__ == "__main__":
    asyncio.run(main())
