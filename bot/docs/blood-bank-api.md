# Blood bank ↔ bot API contract

**Status:** proposed by us, pending the blood bank's confirmation (PRD Open Question 1).
**Audience:** whoever builds or operates the blood bank system.

The bot is a distribution channel. Demand originates in your system and nowhere else —
nobody can raise a request from inside the bot. This document is the entire surface
between us. If something here does not fit your system, tell us and we will change it;
the bot is built against a mock of exactly this contract, so changes are cheap now and
expensive after the pilot starts.

---

## 1. What the bot never receives

The bot does not accept, store, or display anything about a patient: no name, no
attender phone number, no diagnosis, no bed number. A donor only ever sees blood group,
hospital, units and time. Please do not put patient details in `notes` — it is rendered
verbatim into a message that gets forwarded through WhatsApp groups.

## 2. Base URL and versioning

```
https://<bot-host>/v1
```

Breaking changes get a new prefix (`/v2`). Adding an optional field is not breaking.

## 3. Authentication

Every call carries three headers:

| Header | Value |
|---|---|
| `X-Blood-Bank-Id` | Your tenant id, issued by us (e.g. `ekm_district_bank`) |
| `X-Timestamp` | Unix seconds, as a string |
| `X-Signature` | `sha256=` + hex HMAC-SHA256 over `"<X-Timestamp>.<raw request body>"`, keyed with your shared secret |

The body is signed **byte for byte as sent**. Sign the exact bytes you put on the wire —
re-serialising the JSON after signing will change the bytes and fail verification. For
GET requests the body is empty, so sign `"<timestamp>."`.

Requests more than **5 minutes** from our clock are rejected, which is what stops a
captured call being replayed later. Please run NTP.

```python
import hashlib, hmac, json, time, httpx

secret = "..."
body = json.dumps(payload, separators=(",", ":")).encode()  # exact bytes
ts = str(int(time.time()))
sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()

httpx.post(
    "https://bot-host/v1/requests",
    content=body,  # not json=, or the bytes change
    headers={
        "X-Blood-Bank-Id": "ekm_district_bank",
        "X-Timestamp": ts,
        "X-Signature": f"sha256={sig}",
        "Content-Type": "application/json",
    },
)
```

Secrets are per bank and rotatable. `401` means unknown bank, bad signature, or a stale
timestamp — we deliberately do not distinguish them in the response.

---

## 4. `POST /v1/requests` — raise demand

Creates a request and starts notifying donors immediately.

```json
{
  "external_id": "BB-2026-000481",
  "blood_group": "O+",
  "units_needed": 3,
  "hospital": {
    "name": "District General Hospital",
    "address": "Hospital Road, Ernakulam — blood bank counter, 2nd floor"
  },
  "district": "Ernakulam",
  "city": "Kochi",
  "needed_by": "2026-09-07T14:00:00+05:30",
  "slot_time": null,
  "exact_match": false,
  "notes": "Ask at the day-care counter"
}
```

| Field | Required | Notes |
|---|---|---|
| `external_id` | ✅ | **Your** id for this request. See idempotency below. |
| `blood_group` | ✅ | The **patient's** group. One of `O-,O+,A-,A+,B-,B+,AB-,AB+`. We apply the compatibility matrix, so an `A+` request also reaches `O+`, `O-` and `A-` donors. |
| `units_needed` | ✅ | 1–50. Distribution stops the instant this many donors are confirmed. |
| `hospital.name`, `hospital.address` | ✅ | Shown to confirmed donors. Put the *counter* in the address — donors get lost. |
| `district` | ✅ | Hard filter. Only donors registered in this district are notified. Must match our district list exactly. |
| `city` | | Orders the waves (same city first). Never excludes anyone. |
| `needed_by` | ✅ | Must be in the future. Send an explicit offset; a naive timestamp is read as UTC. |
| `slot_time` | | Only if you assign appointment slots. Absent means donors are told "any time before `needed_by`". **This is Open Question 2 — tell us which model you use.** |
| `exact_match` | | `true` restricts to the identical group instead of the matrix. |
| `notes` | | ≤ 300 chars, shown on the card. No patient data. |

**Response `201`:**

```json
{
  "public_id": "K7M2QX9P",
  "status": "OPEN",
  "blood_group": "O+",
  "units_needed": 3,
  "confirmed_count": 0,
  "completed_count": 0,
  "deep_link": "https://t.me/your_bot?start=req_K7M2QX9P",
  "needed_by": "2026-09-07T08:30:00Z",
  "created": true
}
```

`deep_link` is what volunteer admins forward. Anyone who taps it registers (if new) and
lands on this request.

### Idempotency

`external_id` is unique per bank. Retrying a request you already sent returns the
**original** request with `"created": false` and does **not** notify anyone a second
time. Retry freely on timeout — that is the intended behaviour, not a fallback.

### Errors

| Code | Meaning |
|---|---|
| `401` | Unknown bank, bad signature, or stale timestamp |
| `422` | Validation failed — unknown blood group, `needed_by` in the past, `slot_time` after `needed_by`, missing field |

---

## 5. `GET /v1/requests/{public_id}` — check progress

Returns the same shape as above with live `confirmed_count` / `completed_count`.
Poll this, or read the counts back from `POST /completions`.

`404` if the request belongs to another bank — a bank cannot probe another bank's ids.

---

## 6. `GET /v1/requests/{public_id}/donors` — who to expect

The roster for your counter staff. **This is the only place donor contact details leave
the bot**, and only ever to the bank that raised the request.

```json
{
  "public_id": "K7M2QX9P",
  "donors": [
    {
      "telegram_user_id": 884412299,
      "name": "Anitha R",
      "phone": "+919847012345",
      "blood_group": "O+",
      "status": "CONFIRMED",
      "confirmed_at": "2026-09-06T11:02:41Z"
    }
  ]
}
```

`phone` is verified — Telegram supplied it, the donor did not type it.

---

## 7. `POST /v1/requests/{public_id}/completions` — report collected units

This is what keeps donor cooldowns accurate, and PRD goal 4 (≥95% of donations recorded)
depends on it. Please call it the same day.

```json
{
  "donations": [
    { "telegram_user_id": 884412299, "donated_at": "2026-09-07", "blood_group": "O+" },
    { "phone": "+919847098765", "donated_at": "2026-09-07" }
  ]
}
```

Identify the donor by `telegram_user_id` (preferred, from the roster) or `phone`. Send
`blood_group` when you typed them on site — it corrects an "I don't know" registration
and makes that donor matchable from then on.

Each completion:

- sets the donor's last-donation date and next-eligible date (90 days male, 120 female),
- sends the donor a thank-you naming when they can donate again,
- closes the request once every unit is accounted for.

**A donor who walked in without confirming in the bot still counts.** You are the
authority on who actually gave blood; send them and we will record it.

**Response `200`:**

```json
{
  "public_id": "K7M2QX9P",
  "completed_count": 2,
  "results": [
    { "donor_id": 884412299, "recorded": true,  "detail": "recorded" },
    { "donor_id": 771002288, "recorded": false, "detail": "already recorded" }
  ]
}
```

Per-donation results rather than a single status: one unmatched donor does not fail the
batch. `recorded: false` with `"already recorded"` means a safe retry.

---

## 8. `POST /v1/requests/{public_id}/close` — withdraw or finish

```json
{ "status": "CANCELLED", "reason": "patient stabilised" }
```

`status` is `CANCELLED` (no longer needed) or `COMPLETED` (all units collected).
Closing stops all further notifications and clears the Accept button from every
unanswered donor card, so nobody travels for a request that is over. **Please call this
whenever demand disappears** — it is the single biggest lever on donor trust.

---

## 9. What we need from you

| # | Question | Why it blocks us |
|---|---|---|
| 1 | Can you sign requests as described, or do you need an alternative (mTLS, bearer token)? | Auth is the only part we cannot mock away |
| 2 | Do you assign appointment **slots**, or is it "arrive before `needed_by`"? | Changes the confirmation message and whether `slot_time` is required |
| 3 | Do you have a **sandbox** we can point staging at? | Otherwise we test against our mock only |
| 4 | Who calls `/completions`, and how soon after a donation? | Cooldown accuracy, PRD goal 4 |
| 5 | Confirm the district list matches yours exactly | A mismatch silently notifies nobody |
| 6 | Will you consume `GET /donors`, or should we push confirmations to a webhook of yours? | Only affects whether we build an outbound direction |

---

## 10. Testing without us

The bot runs against a local mock. To exercise this contract end to end:

```bash
python -m app.main                                    # bot + API on :8080
python scripts/seed_donors.py --district Ernakulam    # a synthetic donor pool
python scripts/mock_blood_bank.py create --group O+ --units 2
python scripts/mock_blood_bank.py status <public_id>
python scripts/mock_blood_bank.py complete <public_id> --telegram-id <id>
```

`scripts/mock_blood_bank.py` is a reference client — the signing code in it is the
shortest correct implementation of section 3, and you are welcome to copy it.
