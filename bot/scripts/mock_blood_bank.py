"""Reference client for the blood bank API -- and the mock that unblocks Phase 1.

The real integration is gated on the bank's contract (PRD Open Question 1), so the bot is
developed against this. The signing code below is the shortest correct implementation of
docs/blood-bank-api.md section 3; the bank is welcome to copy it.

    python scripts/mock_blood_bank.py create --group O+ --units 2
    python scripts/mock_blood_bank.py status K7M2QX9P
    python scripts/mock_blood_bank.py donors K7M2QX9P
    python scripts/mock_blood_bank.py complete K7M2QX9P --telegram-id 884412299
    python scripts/mock_blood_bank.py close K7M2QX9P --status CANCELLED
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
from datetime import UTC, date, datetime, timedelta

import httpx

from app.config import settings

DEFAULT_BANK = "demo_bank"


def sign(secret: str, body: bytes) -> dict[str, str]:
    """Headers for one call. The body must be the exact bytes sent on the wire."""
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {
        "X-Blood-Bank-Id": DEFAULT_BANK,
        "X-Timestamp": timestamp,
        "X-Signature": f"sha256={digest}",
        "Content-Type": "application/json",
    }


def call(method: str, path: str, payload: dict | None, base: str, secret: str) -> httpx.Response:
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else b""
    response = httpx.request(
        method, f"{base}{path}", content=body, headers=sign(secret, body), timeout=30
    )
    print(f"{method} {path} -> {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except ValueError:
        print(response.text)
    return response


def cmd_create(args, base: str, secret: str) -> None:
    needed_by = datetime.now(UTC) + timedelta(hours=args.hours)
    payload = {
        "external_id": args.external_id or f"mock-{int(time.time())}",
        "blood_group": args.group,
        "units_needed": args.units,
        "hospital": {"name": args.hospital, "address": args.address},
        "district": args.district,
        "city": args.city,
        "needed_by": needed_by.isoformat(),
        "exact_match": args.exact_match,
    }
    if args.notes:
        payload["notes"] = args.notes
    if args.slot_hours is not None:
        payload["slot_time"] = (datetime.now(UTC) + timedelta(hours=args.slot_hours)).isoformat()

    response = call("POST", "/v1/requests", payload, base, secret)
    if response.status_code == 201:
        print(f"\nForward this link:\n  {response.json()['deep_link']}")


def cmd_status(args, base: str, secret: str) -> None:
    call("GET", f"/v1/requests/{args.public_id}", None, base, secret)


def cmd_donors(args, base: str, secret: str) -> None:
    call("GET", f"/v1/requests/{args.public_id}/donors", None, base, secret)


def cmd_complete(args, base: str, secret: str) -> None:
    donation: dict = {"donated_at": (args.donated_at or date.today().isoformat())}
    if args.telegram_id:
        donation["telegram_user_id"] = args.telegram_id
    if args.phone:
        donation["phone"] = args.phone
    if args.group:
        donation["blood_group"] = args.group
    call(
        "POST",
        f"/v1/requests/{args.public_id}/completions",
        {"donations": [donation]},
        base,
        secret,
    )


def cmd_close(args, base: str, secret: str) -> None:
    call(
        "POST",
        f"/v1/requests/{args.public_id}/close",
        {"status": args.status, "reason": args.reason},
        base,
        secret,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=f"http://127.0.0.1:{settings.api_port}")
    parser.add_argument("--secret", default=None, help="defaults to the demo_bank secret in .env")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="raise a request")
    create.add_argument("--group", default="O+")
    create.add_argument("--units", type=int, default=2)
    create.add_argument("--district", default="Ernakulam")
    create.add_argument("--city", default="Kochi")
    create.add_argument("--hospital", default="District General Hospital")
    create.add_argument("--address", default="Hospital Road, Ernakulam - blood bank counter")
    create.add_argument("--hours", type=float, default=6, help="hours until needed_by")
    create.add_argument("--slot-hours", type=float, default=None, help="assign a slot this far out")
    create.add_argument("--notes", default=None)
    create.add_argument("--exact-match", action="store_true")
    create.add_argument("--external-id", default=None, help="repeat one to test idempotency")
    create.set_defaults(func=cmd_create)

    status = sub.add_parser("status", help="read a request")
    status.add_argument("public_id")
    status.set_defaults(func=cmd_status)

    donors = sub.add_parser("donors", help="confirmed donor roster")
    donors.add_argument("public_id")
    donors.set_defaults(func=cmd_donors)

    complete = sub.add_parser("complete", help="report a collected donation")
    complete.add_argument("public_id")
    complete.add_argument("--telegram-id", type=int, default=None)
    complete.add_argument("--phone", default=None)
    complete.add_argument("--group", default=None, help="corrects an unknown blood group")
    complete.add_argument("--donated-at", default=None, help="YYYY-MM-DD, defaults to today")
    complete.set_defaults(func=cmd_complete)

    close = sub.add_parser("close", help="withdraw or finish a request")
    close.add_argument("public_id")
    close.add_argument("--status", choices=["CANCELLED", "COMPLETED"], default="COMPLETED")
    close.add_argument("--reason", default=None)
    close.set_defaults(func=cmd_close)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    secret = args.secret or settings.blood_bank_secrets.get(DEFAULT_BANK)
    if not secret:
        print(f"No secret for '{DEFAULT_BANK}'. Set BLOOD_BANK_SECRETS or pass --secret.")
        return 1
    try:
        args.func(args, args.base.rstrip("/"), secret)
    except httpx.ConnectError:
        print(f"Could not reach {args.base}. Is `python -m app.main` running?")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
