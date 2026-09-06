"""The blood bank integration: auth, idempotent intake, and the completion loop."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.auth import expected_signature
from app.api.main import create_app
from app.enums import DonorRequestStatus, RequestStatus
from app.models import BloodRequest, Donor, DonorRequest
from tests.conftest import make_donor

SECRET = "test-secret"


@pytest_asyncio.fixture
async def client(session, bot):
    app = create_app(bot)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def sign(body: bytes, *, bank: str = "demo_bank", secret: str = SECRET, ts: str | None = None):
    ts = ts or str(int(time.time()))
    return {
        "X-Blood-Bank-Id": bank,
        "X-Timestamp": ts,
        "X-Signature": expected_signature(secret, ts, body),
        "Content-Type": "application/json",
    }


def request_payload(**overrides) -> dict:
    payload = {
        "external_id": "bank-req-001",
        "blood_group": "O+",
        "units_needed": 2,
        "hospital": {"name": "General Hospital", "address": "MG Road, Kochi"},
        "district": "Ernakulam",
        "city": "Kochi",
        "needed_by": (datetime.now(UTC) + timedelta(hours=6)).isoformat(),
    }
    payload.update(overrides)
    return payload


async def post_request(client, **overrides):
    body = json.dumps(request_payload(**overrides)).encode()
    return await client.post("/v1/requests", content=body, headers=sign(body))


# --------------------------------------------------------------------------------------
# Auth (P0-1)
# --------------------------------------------------------------------------------------


async def test_unsigned_request_is_rejected(client):
    body = json.dumps(request_payload()).encode()
    response = await client.post("/v1/requests", content=body)
    assert response.status_code == 422  # missing required headers


async def test_bad_signature_is_rejected(client):
    body = json.dumps(request_payload()).encode()
    headers = sign(body, secret="wrong-secret")
    response = await client.post("/v1/requests", content=body, headers=headers)
    assert response.status_code == 401


async def test_unknown_blood_bank_is_rejected(client):
    body = json.dumps(request_payload()).encode()
    response = await client.post("/v1/requests", content=body, headers=sign(body, bank="nobody"))
    assert response.status_code == 401


async def test_tampered_body_is_rejected(client):
    body = json.dumps(request_payload()).encode()
    headers = sign(body)
    tampered = json.dumps(request_payload(units_needed=99)).encode()
    response = await client.post("/v1/requests", content=tampered, headers=headers)
    assert response.status_code == 401


async def test_stale_timestamp_is_rejected(client):
    body = json.dumps(request_payload()).encode()
    old = str(int(time.time()) - 3600)
    response = await client.post("/v1/requests", content=body, headers=sign(body, ts=old))
    assert response.status_code == 401


# --------------------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------------------


async def test_valid_request_is_created_and_returns_a_deep_link(client):
    response = await post_request(client)
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["status"] == RequestStatus.OPEN
    assert body["deep_link"].endswith(f"?start=req_{body['public_id']}")
    assert len(f"req_{body['public_id']}") <= 64


async def test_retried_post_does_not_create_a_second_request(client, session):
    first = await post_request(client)
    second = await post_request(client)

    assert first.json()["public_id"] == second.json()["public_id"]
    assert second.json()["created"] is False
    count = len((await session.scalars(select(BloodRequest))).all())
    assert count == 1


async def test_unknown_blood_group_is_rejected(client):
    response = await post_request(client, blood_group="Z+")
    assert response.status_code == 422


async def test_past_deadline_is_rejected(client):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    response = await post_request(client, needed_by=past)
    assert response.status_code == 422


async def test_slot_after_deadline_is_rejected(client):
    late = (datetime.now(UTC) + timedelta(hours=9)).isoformat()
    response = await post_request(client, slot_time=late)
    assert response.status_code == 422


async def test_another_bank_cannot_read_a_request(client):
    public_id = (await post_request(client)).json()["public_id"]
    body = b""
    headers = sign(body, bank="other_bank", secret="other-secret")
    response = await client.get(f"/v1/requests/{public_id}", headers=headers)
    assert response.status_code == 404


# --------------------------------------------------------------------------------------
# Fan-out on intake (P0-5)
# --------------------------------------------------------------------------------------


async def test_creating_a_request_notifies_eligible_donors_only(client, session, bot):
    session.add(make_donor(1, blood_group="O+"))
    session.add(make_donor(2, blood_group="AB+"))  # cannot give to an O+ patient
    session.add(make_donor(3, blood_group="O-", district="Kollam", city="Kollam"))
    await session.commit()

    await post_request(client)

    assert [m["chat_id"] for m in bot.sent] == [1]
    links = (await session.scalars(select(DonorRequest))).all()
    assert [link.donor_id for link in links] == [1]
    assert links[0].card_message_id is not None


async def test_wave_size_caps_the_first_batch(client, session, bot):
    for i in range(1, 6):
        session.add(make_donor(i))
    await session.commit()

    await post_request(client)
    assert len(bot.sent) == 3  # WAVE_SIZE is 3 in the test environment


async def test_card_never_mentions_a_patient(client, session, bot):
    session.add(make_donor(1))
    await session.commit()
    await post_request(client, notes="Ask at the day-care counter")

    card = bot.sent[0]["text"]
    assert "O+" in card and "General Hospital" in card
    assert "day-care counter" in card
    assert "patient" not in card.lower()


# --------------------------------------------------------------------------------------
# Close and complete
# --------------------------------------------------------------------------------------


async def test_close_marks_the_request_and_clears_open_cards(client, session, bot):
    session.add(make_donor(1))
    await session.commit()
    public_id = (await post_request(client)).json()["public_id"]

    body = json.dumps({"status": "CANCELLED", "reason": "patient stabilised"}).encode()
    response = await client.post(
        f"/v1/requests/{public_id}/close", content=body, headers=sign(body)
    )

    assert response.status_code == 200
    assert response.json()["status"] == RequestStatus.CANCELLED
    assert len(bot.edited) == 1


async def test_close_cannot_reopen_a_request(client):
    public_id = (await post_request(client)).json()["public_id"]
    body = json.dumps({"status": "OPEN"}).encode()
    response = await client.post(
        f"/v1/requests/{public_id}/close", content=body, headers=sign(body)
    )
    assert response.status_code == 422


async def test_completion_records_the_donation_and_thanks_the_donor(client, session, bot):
    session.add(make_donor(1))
    await session.commit()
    public_id = (await post_request(client, units_needed=1)).json()["public_id"]

    link = await session.scalar(select(DonorRequest))
    link.status = DonorRequestStatus.CONFIRMED
    await session.commit()

    body = json.dumps({"donations": [{"telegram_user_id": 1, "donated_at": "2026-03-01"}]}).encode()
    response = await client.post(
        f"/v1/requests/{public_id}/completions", content=body, headers=sign(body)
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["recorded"] is True
    assert "30 May 2026" in bot.sent[-1]["text"]  # next eligible date, +90 days


async def test_completion_by_phone_finds_the_donor(client, session):
    donor = make_donor(1)
    session.add(donor)
    await session.commit()
    public_id = (await post_request(client, units_needed=1)).json()["public_id"]

    link = await session.scalar(select(DonorRequest))
    link.status = DonorRequestStatus.CONFIRMED
    await session.commit()

    body = json.dumps({"donations": [{"phone": donor.phone, "donated_at": "2026-03-01"}]}).encode()
    response = await client.post(
        f"/v1/requests/{public_id}/completions", content=body, headers=sign(body)
    )
    assert response.json()["results"][0]["donor_id"] == 1


async def test_completion_for_an_uninvolved_donor_is_reported_not_recorded(client, session):
    session.add(make_donor(1))
    # Another district, so the fan-out never links them to this request.
    session.add(make_donor(2, district="Kollam", city="Kollam"))
    await session.commit()
    public_id = (await post_request(client, units_needed=1)).json()["public_id"]

    body = json.dumps({"donations": [{"telegram_user_id": 2, "donated_at": "2026-03-01"}]}).encode()
    response = await client.post(
        f"/v1/requests/{public_id}/completions", content=body, headers=sign(body)
    )
    result = response.json()["results"][0]
    assert result["recorded"] is False
    assert "not part of this request" in result["detail"]


async def test_walk_in_donation_still_updates_the_cooldown(client, session):
    """The bank is the authority on who gave blood, confirmed in the bot or not."""
    session.add(make_donor(1))
    await session.commit()
    public_id = (await post_request(client, units_needed=1)).json()["public_id"]

    link = await session.scalar(select(DonorRequest))
    assert link.status == DonorRequestStatus.NOTIFIED  # never tapped Accept

    body = json.dumps({"donations": [{"telegram_user_id": 1, "donated_at": "2026-03-01"}]}).encode()
    response = await client.post(
        f"/v1/requests/{public_id}/completions", content=body, headers=sign(body)
    )

    assert response.json()["results"][0]["recorded"] is True
    donor = await session.get(Donor, 1)
    await session.refresh(donor)
    assert donor.last_donation_date.isoformat() == "2026-03-01"


async def test_completion_corrects_an_unknown_blood_group(client, session):
    session.add(make_donor(1, blood_group="O+"))
    await session.commit()
    public_id = (await post_request(client, units_needed=1)).json()["public_id"]

    body = json.dumps(
        {"donations": [{"telegram_user_id": 1, "donated_at": "2026-03-01", "blood_group": "O-"}]}
    ).encode()
    await client.post(f"/v1/requests/{public_id}/completions", content=body, headers=sign(body))

    donor = await session.get(Donor, 1)
    await session.refresh(donor)
    assert donor.blood_group == "O-"
    assert donor.blood_group_verified is True


async def test_confirmed_donor_roster_is_scoped_to_the_owning_bank(client, session):
    session.add(make_donor(1))
    await session.commit()
    public_id = (await post_request(client)).json()["public_id"]

    link = await session.scalar(select(DonorRequest))
    link.status = DonorRequestStatus.CONFIRMED
    await session.commit()

    ours = await client.get(f"/v1/requests/{public_id}/donors", headers=sign(b""))
    assert [d["telegram_user_id"] for d in ours.json()["donors"]] == [1]

    theirs = await client.get(
        f"/v1/requests/{public_id}/donors",
        headers=sign(b"", bank="other_bank", secret="other-secret"),
    )
    assert theirs.status_code == 404


async def test_healthz(client):
    assert (await client.get("/healthz")).json() == {"status": "ok"}
