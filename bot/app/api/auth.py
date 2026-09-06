"""Request signing for the blood bank integration (PRD P0-1).

Every call carries three headers:

    X-Blood-Bank-Id  the caller's tenant id
    X-Timestamp      unix seconds, must be within MAX_SKEW of our clock
    X-Signature      sha256=<hex of HMAC-SHA256(secret, "<timestamp>.<raw body>")>

Signing the timestamp alongside the body is what stops a captured request being replayed
later; the shared secret is per bank, so revoking one bank does not touch another.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request, status

from app.config import settings

MAX_SKEW_SECONDS = 300


def expected_signature(secret: str, timestamp: str, body: bytes) -> str:
    payload = timestamp.encode() + b"." + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def verify_signature(
    request: Request,
    x_blood_bank_id: str = Header(...),
    x_timestamp: str = Header(...),
    x_signature: str = Header(...),
) -> str:
    """FastAPI dependency. Returns the authenticated blood bank id."""
    secret = settings.blood_bank_secrets.get(x_blood_bank_id)
    if secret is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown blood bank")

    try:
        skew = abs(time.time() - int(x_timestamp))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad timestamp") from exc
    if skew > MAX_SKEW_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "timestamp outside allowed window")

    body = await request.body()
    if not hmac.compare_digest(expected_signature(secret, x_timestamp, body), x_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")

    return x_blood_bank_id
