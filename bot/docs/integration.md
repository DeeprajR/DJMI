# How the three modules fit together

One PostgreSQL database. Three programs. Two shared tables.

```
Module 1  Doctor app        ─┐
Module 2  Blood bank        ─┼─ one Next.js app (DJMI repo), one Postgres
Module 3  Donor bot (this)  ─┘   bot tables live in schema `donor_bot`
```

```
Doctor submits request ──▶ blood_requests (status = submitted)
                                      │
Bank decides  ◀───────────────────────┘
  issue bags from stock (oldest expiry first)
  shortfall?  ──▶ INSERT donor_demand (status = open)
  group < floor? ──▶ INSERT donor_demand (trigger = stock_floor)
                                      │
Bot ticker (every TICK_SECONDS) ◀─────┘
  imports open rows → request card → waves of donors + admin cards
  writes back: bot_public_id, confirmed/waitlisted/completed/notified, status
  each confirmed donor → INSERT donor_demand_confirmations
                                      │
Counter marks donated / no-show / cancelled ─┘
  bot acknowledges → cooldown updated → thank-you sent → demand completed
```

## The contract: two tables in `public`

Defined by Drizzle in the hospital repo (`src/db/schema/blood-bank.ts`); mirrored as
SQLAlchemy Core tables in [app/integration/demand.py](../app/integration/demand.py).
The bot never creates them — `npm run db:migrate` does.

### `donor_demand` — bank → bot

| Column | Written by | Meaning |
|---|---|---|
| `id`, `trigger`, `blood_request_id`, `blood_group`, `product`, `units`, `date_needed` | bank | What is needed. `trigger` is `request_shortfall` or `stock_floor` |
| `hospital_name`, `hospital_address`, `district`, `city`, `notes` | bank | Snapshotted from bank settings; what donors are told |
| `status` | both | bank: `open` → `cancelled`; bot: `open` → `fulfilled` → `completed` / `expired` |
| `bot_public_id`, `bot_imported_at` | bot | Set once imported; `bot_public_id` is the deep-link id |
| `confirmed_units`, `waitlisted_units`, `completed_units`, `notified_donors` | bot | Live progress for the dashboard |

The bot polls `status = 'open' AND bot_public_id IS NULL`. Import is idempotent — the
demand id is the bot's `external_id`, so a row is never fanned out twice.

### `donor_demand_confirmations` — bot → bank → bot

| Column | Written by | Meaning |
|---|---|---|
| `demand_id`, `telegram_user_id`, `donor_name`, `donor_phone`, `blood_group`, `confirmed_at` | bot | A donor who passed screening and holds a unit. The roster |
| `status` | both | bot: `confirmed`; bank: `completed` / `no_show` / `cancelled` |
| `donated_at`, `bag_rfid_tag`, `marked_by` | bank | What happened at the counter |
| `bot_acknowledged_at` | bot | Set once the bot has updated the donor and sent the thank-you |

`(demand_id, telegram_user_id)` is unique. A `cancelled` mark releases the unit on the
bot side; `completed` rolls the donor's cooldown forward and, once every unit is in,
closes the demand as `completed`.

### Dates

The bank records a **day** (`date_needed`); donors are told "Needed by Sun 7 Sep" and
the request expires at 23:59 local time that day. API-originated requests keep their
exact time.

## What each side owns

| | Module 2 (bank) | Module 3 (bot) |
|---|---|---|
| Creates | `donor_demand` rows | bot request, waves, `donor_demand_confirmations` rows |
| Updates | `donor_demand.status → cancelled`; confirmation status/donated_at | progress counters, `donor_demand.status`, `bot_acknowledged_at` |
| Never touches | anything in `donor_bot.*` | `blood_bags`, `bank_decisions`, `bank_settings`, `blood_requests` |

## Alternative: the HTTP API

[blood-bank-api.md](blood-bank-api.md) still describes the signed HTTP interface. It
remains available for an external blood bank that cannot share the database; for this
deployment `BANK_SYNC_ENABLED=true` and the API is unused.

## Setup

```powershell
# once: create the database and the bot schema, print the .env lines for both repos
python scripts/setup_shared_db.py postgresql://postgres:<password>@127.0.0.1:5432

# hospital app
cd ..
npm run db:migrate
npm run seed:admin
npm run seed:bank -- --email bank@example.com --password <12+ chars> --name "Blood Bank"
npm run dev                       # http://localhost:3000 → sign in → /bank

# bot
cd ../..
python scripts/add_admin.py <telegram id> --name "Volunteer" --district Kozhikode
python -m app.main
```

Then: doctor submits a request → `/bank/requests` → decide → shortfall appears on
`/bank/demand` → within a minute the bot sends cards → donor confirms → roster row →
mark **Donated** → donor is thanked.
