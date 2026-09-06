# Blood Connect

**Problem statement: Blood Connect.** A hospital needs blood for a patient. Today that
means a paper request form, a phone call to the blood bank, and — when the shelf is
empty — a WhatsApp forward begging strangers to show up. Blood Connect replaces all
three steps with software that shares one database.

Three apps, one PostgreSQL database, one loop:

| # | App | What it is | Who uses it | Runs at |
|---|---|---|---|---|
| **1** | **Doctor app** | Next.js PWA — patients, admissions, the blood request form, review, submit, sample association | Doctors, hospital admin | `http://localhost:3000` |
| **2** | **Blood bank dashboard** | The same Next.js app, `/bank` — RFID bag inventory, decide each request, raise donor demand, mark donors at the counter | Blood bank staff | `http://localhost:3000/bank` |
| **3** | **Donor bot** | Python/aiogram Telegram bot — finds eligible donors, notifies them in waves, screens them, stops at the unit count | Donors, volunteer admins | Telegram (long polling) + `:8080` |

Modules 1 and 2 are one Next.js codebase at the repo root.
Module 3 is this `bot/` directory. They never call each other over HTTP — the contract is two
tables in the shared database, described in [docs/integration.md](docs/integration.md).

---

## The loop

```
Doctor  ──── submits blood request ────▶  blood_requests (submitted)
 (app 1)                                        │
                                                ▼
Bank    ──── decides at /bank/requests ───  issue bags from stock, oldest expiry first
 (app 2)                                        │
                                    shortfall?  └──▶ INSERT donor_demand (open)
                                    below floor? ───▶ INSERT donor_demand (stock_floor)
                                                │
                                                ▼
Bot     ──── ticker imports open demand ───  waves of 20 eligible donors every 30 min
 (app 3)                                     nearest city first, longest-since-donation first
                                             + a forwardable card to volunteer admins
                                                │
Donor:  Accept ─▶ 6-question screening ─▶ pass ─▶ confirmed ─▶ hospital + time
                                        └▶ fail ─▶ dropped from THIS request only
                                                │
                                                ▼
                                     donor_demand_confirmations  (the counter's roster)
                                                │
Bank    ──── marks Donated / No-show / Cancelled at /bank/demand
                                                │
Bot     ──── cooldown rolled forward, thank-you sent, demand closed
```

Three rules shape the whole system:

**Eligibility is computed, never asked.** Blood-group compatibility, district, age 18–65,
cooldown (90 days male / 120 female, NBTC norms), snooze and opt-out are applied before a
message is sent, so every ping a donor receives is actionable.

**Buttons, not typing.** A donor types exactly one thing during registration: their name.
Dates are button grids; the phone number comes from Telegram's contact share, so it is
verified rather than typed.

**Nothing about the patient leaves the hospital.** A donor card carries blood group,
hospital, units and time. No patient names, no attender numbers. Donor contact details go
back only to the bank that raised the demand.

---

## Setup

### 0. What you need

- **Node.js 20+** and **npm** — apps 1 and 2
- **Python 3.11+** — app 3
- **PostgreSQL 16** — shared by all three. `docker compose up -d postgres` in
  `docker compose up -d postgres` at the repo root is the easiest source; a hosted Neon database also works.
- **A Telegram bot token** from [@BotFather](https://t.me/BotFather) — app 3 only

All three modules live in this one repository:

```
DJMI/                      # apps 1 + 2 — the Next.js hospital app (repo root)
└── bot/                   # app 3 — the donor bot
```

### 1. One database for all three

```powershell
cd ..
docker compose up -d postgres          # or point at your own Postgres / Neon

cd bot
python scripts\setup_shared_db.py postgresql://postgres:postgres@127.0.0.1:5432
```

`setup_shared_db.py` creates the `blood_request` database, creates the bot's isolated
`donor_bot` schema, and **prints the exact `.env` lines for both repos**. It is
idempotent — safe to re-run.

The two codebases split the database cleanly: the Next.js app owns everything in
`public` and creates it with its migrations; the bot owns everything in `donor_bot`.
Neither writes the other's private tables.

### 2. Apps 1 + 2 — the hospital app

```powershell
cd ..
npm install
copy .env.example .env                 # paste in DATABASE_URL from step 1
npm run db:migrate                     # creates every table in `public`
```

Fill in `.env`:

| Variable | Value |
|---|---|
| `DATABASE_URL` | printed by `setup_shared_db.py` |
| `SESSION_SECRET` | 32+ random chars — `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `SEAL_STORAGE_DIR` | any directory **outside** the webroot, for doctor seal PNGs |
| `RFID_READER_TOKEN` | 32+ random chars; the bag reader sends it in `X-Reader-Token` |
| `NEXT_PUBLIC_BOT_USERNAME` | your bot's username, no `@` — used to render donor share links |

No Docker? `npm run db:migrate:local` runs the migrations against an embedded
PostgreSQL instead.

Create the accounts — there are three roles: `admin`, `doctor`, `blood_bank`.

```powershell
npm run seed:admin
npm run seed:doctor -- --email doctor@hospital.local --password <12+ chars> --name "Dr Test" --provisional-reg "KL-12345"
npm run seed:bank   -- --email bank@hospital.local   --password <12+ chars> --name "Blood Bank"
```

After the first admin exists, further doctors are created in the UI at `/admin`.

### 3. App 3 — the donor bot

```powershell
python -m pip install -e ".[dev]"
copy .env.example .env
```

Fill in `.env`:

| Variable | Value |
|---|---|
| `BOT_TOKEN`, `BOT_USERNAME` | from @BotFather |
| `DATABASE_URL` | printed by `setup_shared_db.py` (the `postgresql+asyncpg://` one) |
| `DB_SCHEMA` | `donor_bot` |
| `BANK_SYNC_ENABLED` | `true` — read demand from the bank instead of the HTTP API |

Then whitelist yourself as a volunteer admin, so you receive every new request as a card
with a live counter and a message you can forward:

```powershell
python scripts\add_admin.py <your telegram id> --name "Volunteer" --district Kozhikode
```

Your Telegram id comes from [@userinfobot](https://t.me/userinfobot). Omit `--district`
to receive requests from everywhere.

`python scripts\doctor.py` checks everything between your `.env` and Telegram — token,
network, database, port — and says what to do about each failure. Run it first when
something will not start.

---

## Running all three

Two terminals:

```powershell
# terminal 1 — apps 1 + 2
cd ..
npm run dev                            # http://localhost:3000
```

```powershell
# terminal 2 — app 3
python -m app.main                     # bot + API on :8080 + wave ticker
```

The bot runs as **one process on purpose** — bot, blood-bank HTTP API and wave ticker
share one event loop. Onboarding progress lives in the database rather than in memory, so
a restart never strands a half-registered donor. Telegram allows only one process to poll
a given token, so stop one copy before starting another.

Optional, for testing without real donors:

```powershell
python scripts\seed_donors.py --district Ernakulam --count 40   # synthetic pool
python scripts\inspect_db.py                                    # see what happened
python scripts\seed_donors.py --clear                           # remove them
```

Seeded donors carry negative Telegram ids, so they can never collide with real ones.

---

## Usage — the whole loop, end to end

### 1. Doctor raises a request (app 1)

Sign in at `http://localhost:3000/sign-in` as the doctor.

| Step | Where |
|---|---|
| Upload your seal (PNG, ≤1 MB) | `/profile` |
| Create a patient | `/patients` |
| Admit them — `ip_no` is the admission's identity | `/admissions` |
| Start the request form | `/requests/new?ipNo=<ip_no>` |
| Edit the draft | `/requests/:id` |
| Review every field | `/requests/:id/review` |
| **Submit** — allocates a Request ID `BR-YYYY-NNNNNN` | same page |
| View it, and attach the blood sample | `/requests/:id/view` |

Doctor identity fields are read-only and always come from the authenticated account,
never the form. Once submitted, a request is immutable through the draft endpoints. The
form's wording is frozen verbatim from the paper original.

The app is an installable PWA: the shell works offline, but clinical data routes are
network-only and return `503` with an explicit connectivity message rather than serving
stale records.

### 2. Blood bank decides (app 2)

Sign out, sign in as the `blood_bank` account, open `/bank`.

| Page | What you do there |
|---|---|
| `/bank/inventory` | One row per bag, identified by its RFID tag. Readers post to `POST /api/bank/bags/scan` with `X-Reader-Token` |
| `/bank/requests` | Every submitted request. Issue bags — **oldest expiry first** — and any shortfall on whole blood / packed RBC becomes a `donor_demand` row |
| `/bank/demand` | Live recruitment: units confirmed, waitlisted, donors notified. Plus **recruit for groups below floor** |
| `/bank/settings` | `min_units_per_group` (25 by default) — the stock floor every group is kept at |

The doctor sees the bank's decision on their own request view. Demand raised here is what
the bot picks up.

### 3. The bot recruits (app 3)

Within one tick (`TICK_SECONDS`, 60s by default) the bot imports the open demand and:

- messages **20 eligible donors**, then another 20 every 30 minutes until the units are
  met — nearest city first, longest-since-donation first
- sends every volunteer admin a card with a live counter and a forwardable message
- prints a deep link `t.me/<bot>?start=req_<id>` that anyone can share

A donor who taps the link and is not registered is onboarded first — name, blood group,
district, city, date of birth, last donation date, phone via contact share — then lands
on the request.

A donor who taps **Accept** answers six screening questions. Pass → confirmed, and they
receive the hospital, address and time. Fail → dropped from *this* request only; their
profile is untouched. Accept a request whose last unit was just taken → waitlisted,
rather than answering six questions for a place that no longer exists.

### 4. The counter closes the loop (app 2 → app 3)

Confirmed donors appear on `/bank/demand` as a roster — name and verified phone. Mark
each one **Donated**, **No-show**, or **Cancelled**.

- **Donated** → the bot rolls that donor's cooldown forward and sends the thank-you; when
  every unit is in, the demand closes as `completed`
- **Cancelled** → the unit is released back and the waitlist can be promoted

The bank can also record a **walk-in** donation from someone who never confirmed in the
bot — they are the authority on who actually gave blood, and cooldown accuracy matters
more than tidy state.

### Testing app 3 without a blood bank

The bot also accepts requests over a signed HTTP API
([docs/blood-bank-api.md](docs/blood-bank-api.md)), kept for external banks that cannot
share a database. `scripts/mock_blood_bank.py` is the reference client:

```powershell
python scripts\mock_blood_bank.py create --group O+ --units 2   # prints the deep link
python scripts\mock_blood_bank.py progress <request id>
python scripts\mock_blood_bank.py roster <request id>
python scripts\mock_blood_bank.py complete <request id> --donor <telegram id>
```

Set `BANK_SYNC_ENABLED=false` to use this path instead of the shared database.
[docs/running.md](docs/running.md) walks the bot's whole loop this way, with a
troubleshooting table.

---

## Configuration reference

Everything lives in two `.env` files. Both repos ship a `.env.example`; neither `.env` is
committed.

**`.env` at the repo root** — apps 1 + 2: `DATABASE_URL`, `SESSION_SECRET`,
`SEAL_STORAGE_DIR`, `RFID_READER_TOKEN`, `NEXT_PUBLIC_BOT_USERNAME`, and the `ADMIN_*`
bootstrap values.

**`.env`** — app 3, grouped in [.env.example](.env.example):

| Group | Keys |
|---|---|
| Telegram | `BOT_TOKEN`, `BOT_USERNAME`, `TELEGRAM_TIMEOUT`, `TELEGRAM_RETRIES`, `TELEGRAM_RETRY_DELAY` |
| Database | `DATABASE_URL`, `DB_SCHEMA`, `BANK_SYNC_ENABLED`, `BANK_ID` |
| Inbound API | `API_HOST`, `API_PORT`, `BLOOD_BANK_SECRETS` (per-bank HMAC secrets, JSON) |
| Distribution | `WAVE_SIZE` (20), `WAVE_INTERVAL_MINUTES` (30), `TICK_SECONDS` (60) |
| Eligibility | `COOLDOWN_DAYS_MALE` (90), `COOLDOWN_DAYS_FEMALE` (120), `MIN_AGE` (18), `MAX_AGE` (65) |
| Misc | `LOCALE`, `SUPPORT_CONTACT`, `LOG_LEVEL` |

---

## Tests and quality checks

```powershell
# app 3
python -m pytest                       # 183 tests
python -m ruff check .

# apps 1 + 2
cd ..
npm run test
npm run lint
npm run typecheck
npm run build
```

The bot's tests cover the ABO/Rh matrix, the eligibility predicate (including an
assertion that its SQL and Python forms agree), the screening gate, wave distribution and
escalation, the last-unit race, replayed callbacks, the HTTP API and the shared-database
integration. The hospital app's cover redirect safety, same-origin POST validation, frozen
form wording, contrast pairs, control dimensions and service-worker behavior.

---

## Deploying

[docs/deploy.md](docs/deploy.md) has the full walkthrough. The short version:

| Piece | Runs on |
|---|---|
| Apps 1 + 2 (Next.js) | Vercel — `https://<project>.vercel.app`, HTTPS on the default hostname |
| Database | Neon, or any managed PostgreSQL |
| App 3 (Python) | Any always-on process — a 512 MB VPS under systemd is plenty |

The bot has **no public surface**: the bank hands it work by writing rows, and Telegram is
reached by long polling. It only needs the database URL. One known caveat: doctor seal
images are written to local disk, which on Vercel is per-instance and wiped on every
deploy — `src/lib/storage/seal.ts` needs an object store before doctors rely on seals in
production.

---

## Where things live

### This repo — app 3

| Path | What lives there |
|---|---|
| [app/core/](app/core/) | Compatibility matrix, eligibility predicate, screening gate, state transitions |
| [app/distribution.py](app/distribution.py) | Wave fan-out and the escalation ticker |
| [app/bot/](app/bot/) | Handlers, keyboards, rendering, DB-backed FSM storage, admin cards |
| [app/api/](app/api/) | The blood bank's inbound HTTP API and its HMAC auth |
| [app/integration/demand.py](app/integration/demand.py) | Shared-database sync — imports demand, reports progress and the roster |
| [app/locales/en.yml](app/locales/en.yml) | Every donor-facing string |
| [scripts/](scripts/) | `setup_shared_db.py`, `add_admin.py`, `seed_donors.py`, `mock_blood_bank.py`, `inspect_db.py`, `doctor.py` |
| [docs/bot.md](docs/bot.md) | The bot in depth — design decisions, concurrency, what is not built |
| [docs/running.md](docs/running.md) | Guided end-to-end test of the bot, with a troubleshooting table |
| [docs/integration.md](docs/integration.md) | The two-table contract between bank and bot |
| [docs/blood-bank-api.md](docs/blood-bank-api.md) | The signed HTTP contract, for external banks |
| [docs/deploy.md](docs/deploy.md) | Vercel + Neon + systemd |
| [plan.md](plan.md) | The PRD everything is built to |

### Repo root — apps 1 + 2

| Path | What lives there |
|---|---|
| `src/app/` | Next.js App Router — pages and `/api/*` route handlers |
| `src/app/bank/` | Module 2: inventory, requests, demand, settings |
| `src/db/schema/tables.ts` | Module 1 tables — patients, admissions, requests, samples, sessions, audit log |
| `src/db/schema/blood-bank.ts` | Module 2 tables, **and the two shared with the bot** |
| `drizzle/` | Migrations — the only thing that creates `public` tables |
| `scripts/` | `create-admin.ts`, `create-doctor.ts`, `create-bank-user.ts`, migration and preview helpers |
| `design-system-blood-app.md` | The design system both modules follow |
| `PHASE_CHECKLIST.md` | Build phases 1–10, and what each delivered |

---

## Two details worth knowing before you change things

**The last unit** ([app/core/service.py](app/core/service.py)). `claim_unit` increments
`confirmed_count` in a single UPDATE guarded by `confirmed_count < units_needed`. Two
donors finishing screening at the same instant contend on one row: exactly one UPDATE
matches, so one is confirmed and the other waitlisted. Do not replace this with a
read-then-write.

**Replayed taps.** Telegram redelivers callback queries. Every transition is a conditional
UPDATE guarded on the status it expects, and reports whether it actually moved; a replay
matches nothing and is a no-op. Questionnaire progress lives on the `DonorRequest` row
rather than in FSM memory, so a duplicate tap is caught by comparing the tapped question
index against the answers already recorded — and the flow survives a restart.

---

## Not built yet

**App 3** — the remaining PRD Phase 2 items, in the order worth doing:

- reminder before the slot / needed-by time (P0-9)
- donor cancels after confirming → slot reopens, waitlist promoted (P0-10; `release_unit`
  and the waitlist query exist, the offer flow does not)
- account settings — district, city, phone, last-donation date, snooze, delete my data (P0-13)
- "show me open requests I qualify for" (P0-14)

**Before a real pilot, across all three:**

- **Alembic migrations for the bot.** Its schema is currently `create_all`; the hospital
  app already has Drizzle migrations.
- **Redis FSM storage** if the bot ever runs as more than one process.
- **Object storage for doctor seals** — see the Vercel caveat above.
- **Consent wording reviewed against the DPDP Act 2023.** The text in
  `onboarding.ask_consent` was written by an engineer, not a lawyer.
- **A retention policy.** `event_log` and `audit_log` grow without bound and hold
  health-adjacent data.
- **Malayalam.** Every donor string is already in `app/locales/en.yml` with a per-donor
  `language` column in place; a second file with the same keys needs no handler changes.

---

## License and medical disclaimer

The hospital app (everything outside `bot/`) is licensed under **PolyForm Noncommercial 1.0.0**;
see its `LICENSE`.

This software is provided **AS IS**. It is not medical advice, not a substitute for
clinical judgment, and not clinically validated. It must not be used in a real clinical
environment without appropriate validation, security review, compliance review and
institutional authorization. No claim of regulatory approval or production readiness is
made.
