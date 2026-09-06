# Blood Donor Telegram Bot

A Telegram bot that turns blood-bank demand into confirmed donors at a hospital counter.
Requests originate in the blood bank's own system and arrive over a signed API; the bot
works out who is eligible, notifies them in waves, screens the ones who say yes, and
stops the moment the units are met.

Built to [plan.md](../plan.md) (the PRD). Section references below point back at it.

**It is one of three modules on one PostgreSQL database.** The doctor app (Module 1)
and the blood bank dashboard (Module 2) live in the DJMI repo, checked out at
the repo root; this bot is Module 3. The bank raises demand by inserting a row, the
bot recruits, and the counter's marks flow back — see
[docs/integration.md](integration.md) for the two-table contract.

**Phase 1 is complete and tested** — request intake, onboarding, eligibility, wave
fan-out and the accept → screen → confirm loop (P0-1 … P0-8), plus the completion loop
the API contract needs. Phase 2 (P0-9 … P0-14) is listed at the bottom.

---

## How it works

```
Blood bank ──POST /v1/requests──▶ Bot
                                  ├─▶ eligible donors, in waves of 20 every 30 min
                                  │     nearest city first, longest-since-donation first
                                  │     stops the instant confirmations == units needed
                                  └─▶ deep link  t.me/<bot>?start=req_<id>  to forward

Donor:  Accept ─▶ questionnaire ─▶ pass ─▶ confirmed (if units remain) ─▶ hospital + time
                                └▶ fail ─▶ eliminated from THIS request, profile untouched

Blood bank ──POST /completions──▶ cooldown updated, thank-you sent, request closed
```

Three rules shape the whole codebase:

**Eligibility is computed, never asked.** Blood-group compatibility, district, age 18–65,
cooldown (90 days male / 120 female, NBTC norms), snooze and opt-out are all applied
before a message is sent, so every ping a donor receives is actionable. The same
predicate exists as SQL (to pick a wave) and as Python (to check one donor arriving on a
deep link), and a test asserts the two agree.

**Buttons, not typing.** A donor types exactly one thing during registration: their name.
Both dates are button grids; the phone number comes from Telegram's contact share, so it
is verified rather than typed.

**Nothing about the patient.** A card carries blood group, hospital, units and time. No
names, no attender numbers. The only place donor contact details leave the bot is the
confirmed-donor roster, and only to the bank that raised the request.

---

## Running it

**Full walkthrough: [docs/running.md](running.md)** — setup, a guided test of the
whole loop, and a troubleshooting table. The short version:

```bash
python -m pip install -e ".[dev]"
cp .env.example .env          # set BOT_TOKEN and BOT_USERNAME from @BotFather
python -m app.main            # bot (long polling) + API on :8080 + wave ticker
```

Then, in another terminal:

```bash
python scripts/seed_donors.py --district Ernakulam --count 40   # synthetic pool
python scripts/mock_blood_bank.py create --group O+ --units 2   # raise a request
python scripts/inspect_db.py                                    # see what happened
```

`create` prints the deep link. Open it in Telegram to register yourself and land on the
request. Seeded donors carry negative Telegram ids so they can never collide with real
ones; `--clear` removes them.

Everything runs in one process on purpose. Onboarding progress is stored in the
database, not in memory, so a restart or deploy does not strand a half-registered donor.
Telegram still allows only one process to poll a given token.

```bash
python -m pytest          # 183 tests
python -m ruff check .
```

---

## Layout

| Path | What lives there |
|---|---|
| [app/core/compatibility.py](../app/core/compatibility.py) | ABO/Rh matrix — which donor groups may give to a recipient |
| [app/core/eligibility.py](../app/core/eligibility.py) | The eligibility predicate, in SQL and in Python (PRD 7.4) |
| [app/core/questionnaire.py](../app/core/questionnaire.py) | The screening gate and what each failure means (PRD 7.6) |
| [app/core/service.py](../app/core/service.py) | State transitions, the last-unit guard, completion |
| [app/distribution.py](../app/distribution.py) | Wave fan-out and the escalation ticker (PRD 7.5) |
| [app/bot/handlers/onboarding.py](../app/bot/handlers/onboarding.py) | Registration and deep-link entry (PRD 7.3) |
| [app/bot/handlers/requests.py](../app/bot/handlers/requests.py) | Accept, decline, screen, confirm, waitlist |
| [app/api/](../app/api/) | The blood bank's inbound API and its HMAC auth |
| [app/bot/storage.py](../app/bot/storage.py) | FSM state in the database, so restarts do not drop onboarding |
| [app/locales/en.yml](../app/locales/en.yml) | Every donor-facing string |
| [docs/blood-bank-api.md](blood-bank-api.md) | The contract to hand the blood bank |
| [docs/running.md](running.md) | How to run and test it end to end |
| [docs/integration.md](integration.md) | The shared-database contract with the blood bank dashboard |
| [app/integration/demand.py](../app/integration/demand.py) | Imports bank demand, reports progress and the roster back |
| [app/bot/admin.py](../app/bot/admin.py) | Volunteer admin cards with a live counter and the forwardable message |
| [scripts/](../scripts/) | `mock_blood_bank.py` (reference API client), `seed_donors.py`, `inspect_db.py` |

### Two details worth knowing before you change things

**The last unit** ([app/core/service.py](../app/core/service.py)). `claim_unit` increments
`confirmed_count` in a single UPDATE guarded by `confirmed_count < units_needed`. Two
donors finishing screening at the same instant contend on one row: exactly one UPDATE
matches, so one is confirmed and the other is waitlisted. Do not replace this with a
read-then-write.

**Replayed taps.** Telegram redelivers callback queries. Every transition is a
conditional UPDATE guarded on the status it expects and returns whether it actually
moved; a replay matches nothing and is a no-op. Questionnaire progress lives on the
`DonorRequest` row rather than in FSM memory, so a duplicate tap is caught by comparing
the tapped question index against the answers already recorded — and the flow survives a
restart.

---

## Decisions taken while building

Three of the PRD's blocking open questions had to be answered to start. These are
reversible; flag any you disagree with.

| Question | Answer taken | Reversibility |
|---|---|---|
| v1 language (PRD Open Question 3) | **English**, with every string in `app/locales/en.yml` and a per-donor `language` column already in place | Malayalam is a second file with the same keys — no handler changes |
| Appointment slots (Open Question 2) | **"Arrive before `needed_by`"**, with an optional `slot_time` the bank may send per request | Both already render; the bank's answer only decides which is used |
| Blood bank API (Open Question 1) | **Proposed the contract ourselves** in [docs/blood-bank-api.md](blood-bank-api.md), built against a mock | Send them the doc; section 9 lists the six things we need back |

Smaller calls, each isolated to one place:

- **HMAC-SHA256 over `timestamp.body`, per-bank secret.** Signing the timestamp is what
  prevents replay. Swappable in [app/api/auth.py](../app/api/auth.py) if the bank needs
  mTLS or a bearer token.
- **`blood_bank_id` on every request from day one.** Multi-tenant is a PRD P2, but
  retrofitting a tenant column later is expensive and adding it now costs nothing.
- **A `next_wave_at` column polled by a ticker**, not an in-memory timer, so a restart
  mid-request resumes escalation instead of stranding it.
- **A blocked donor is opted out on the spot** and their link row deleted, so they are
  neither retried forever nor left as a phantom in the counts — and the block-rate
  metric (PRD 9) stays honest.
- **The bank can record a walk-in donation** from a donor who never confirmed in the bot.
  They are the authority on who gave blood, and donor cooldown accuracy (PRD goal 4)
  matters more than tidy state.
- **A donor who accepts a just-filled request joins the waitlist** rather than answering
  six questions for a place that no longer exists.

## Not built yet

Phase 2 from the PRD, in the order it is worth doing. (P0-11 completion and P0-12 admin
cards are done; the completion loop now runs off the blood bank's counter marks.)

- **P0-9** reminder before the slot / needed-by time (the confirmation message itself is done)
- **P0-10** donor cancels after confirming → slot reopens, waitlist promoted (`release_unit` and the waitlist query exist; the offer flow does not)
- **P0-13** account settings: district, city, phone, last-donation date, snooze, delete my data
- **P0-14** "show me open requests I qualify for"

Also outstanding before a real pilot:

- **Alembic migrations.** Schema is currently `create_all`; add migrations before the pilot widens beyond one district.
- **Redis FSM storage** if the bot runs as more than one process.
- **Consent wording reviewed against the DPDP Act 2023** — the text in `onboarding.ask_consent` is a placeholder written by an engineer, not a lawyer (PRD Open Question, legal).
- **A retention policy.** `event_log` grows without bound and holds health-adjacent data.
