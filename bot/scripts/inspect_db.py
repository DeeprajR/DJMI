"""Print the current state of the database -- requests, donors, and who responded.

Read-only. Useful while testing to answer "why did nobody get notified?" without
opening a SQL client.

    python scripts/inspect_db.py
    python scripts/inspect_db.py --events        # also show the transition log
    python scripts/inspect_db.py --all-donors    # include seeded (negative-id) donors
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db import session_scope
from app.models import BloodRequest, Donor, DonorRequest, EventLog


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


async def show(show_events: bool, all_donors: bool) -> None:
    async with session_scope() as session:
        rule("REQUESTS")
        requests = list(await session.scalars(select(BloodRequest).order_by(BloodRequest.id)))
        if not requests:
            print("(none yet -- create one with scripts/mock_blood_bank.py create)")
        for r in requests:
            print(
                f"{r.public_id}  {r.blood_group:<4} {r.status:<9} "
                f"confirmed {r.confirmed_count}/{r.units_needed}  "
                f"completed {r.completed_count}  "
                f"{r.city or '-'}, {r.district}  wave={r.wave_index}"
            )

        rule("DONORS" if all_donors else "REAL DONORS (seeded ones hidden)")
        query = select(Donor).order_by(Donor.telegram_user_id.desc())
        if not all_donors:
            query = query.where(Donor.telegram_user_id > 0)
        donors = list(await session.scalars(query))
        if not donors:
            print("(none -- send /start to your bot in Telegram)")
        for d in donors:
            flags = []
            if not d.is_registered:
                flags.append("UNFINISHED")
            if d.opted_out:
                flags.append("OPTED-OUT")
            if d.snoozed_until:
                flags.append(f"snoozed→{d.snoozed_until}")
            if d.review_flag:
                flags.append(f"review:{d.review_reason}")
            print(
                f"{d.telegram_user_id:>12}  {(d.full_name or '?'):<16} {d.blood_group:<7} "
                f"{(d.city or '-'):<14} last_donation={d.last_donation_date or 'never'} "
                f"{' '.join(flags)}"
            )

        rule("RESPONSES")
        links = list(await session.scalars(select(DonorRequest).order_by(DonorRequest.id)))
        if not links:
            print("(nobody has been notified yet)")
        by_request = {r.id: r.public_id for r in requests}
        for link in links:
            print(
                f"{by_request.get(link.request_id, link.request_id):<10} "
                f"donor={link.donor_id:<12} {link.status:<15} wave={link.wave} "
                f"answers={len(link.answers or {})}"
                + (f" reason={link.eliminated_reason}" if link.eliminated_reason else "")
            )

        if show_events:
            rule("EVENT LOG")
            for e in await session.scalars(select(EventLog).order_by(EventLog.id)):
                stamp = e.at.strftime("%H:%M:%S")
                print(f"{stamp}  {e.event:<32} donor={e.donor_id or '-'} req={e.request_id or '-'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--events", action="store_true", help="also print the transition log")
    parser.add_argument("--all-donors", action="store_true", help="include seeded donors")
    args = parser.parse_args()
    asyncio.run(show(args.events, args.all_donors))


if __name__ == "__main__":
    main()
