"""Short, URL-safe public IDs.

Telegram's `start` payload is capped at 64 chars (PRD 12), and the payload also has to
survive being pasted into WhatsApp forwards, so IDs are short and use an unambiguous
alphabet (no 0/O/1/I/l).
"""

from __future__ import annotations

import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
DEFAULT_LENGTH = 8


def new_public_id(length: int = DEFAULT_LENGTH) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def parse_start_payload(payload: str | None) -> str | None:
    """Return the request public id from a `req_<id>` start payload, else None."""
    if not payload:
        return None
    payload = payload.strip()
    if not payload.startswith("req_"):
        return None
    public_id = payload[4:].upper()
    if not public_id or any(c not in ALPHABET for c in public_id):
        return None
    return public_id
