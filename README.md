# Blood Connect

A hospital needs blood for a patient. Today that means a paper request form, a phone call
to the blood bank, and — when the shelf is empty — a WhatsApp forward begging strangers to
show up. Blood Connect replaces all three steps with software that shares one database.

Three modules, one PostgreSQL database, one loop:

| # | Module | What it is | Lives in |
|---|---|---|---|
| **1** | **Doctor app** | Next.js PWA — patients, admissions, the blood request form, review, submit, sample association | repo root (`src/`) |
| **2** | **Blood bank dashboard** | The same Next.js app under `/bank` — RFID bag inventory, decide each request, raise donor demand | repo root (`src/app/bank/`) |
| **3** | **Donor bot** | Python/aiogram Telegram bot — finds eligible donors, notifies them in waves, screens them, stops at the unit count | [`bot/`](bot/) |

Modules 1 and 2 are one Next.js codebase deployed to Vercel. Module 3 is a long-running
Python process that cannot run on Vercel. They never call each other over HTTP — the
contract is two tables in the shared database, described in
[bot/docs/integration.md](bot/docs/integration.md).

The Next.js app owns everything in the `public` schema and creates it with Drizzle
migrations; the bot owns the `donor_bot` schema. Neither writes the other's tables.

Current Status:
- QA test = IN-PROGRESS
- Stock update using RFID = Pending
- Telegram Bot deployment = Pending

## Quick start

```bash
# modules 1 + 2 — from the repo root
npm install
cp .env.example .env          # DATABASE_URL, SESSION_SECRET, RFID_READER_TOKEN, NEXT_PUBLIC_BOT_USERNAME
npm run db:migrate
npm run dev                   # http://localhost:3000
```

```bash
# module 3 — from bot/
cd bot
python -m pip install -e ".[dev]"
cp .env.example .env          # BOT_TOKEN, BOT_USERNAME, DATABASE_URL, DB_SCHEMA=donor_bot
python -m app.main            # bot + inbound API on :8080 + wave ticker
```

Only **one** copy of the bot may run at a time — Telegram rejects a second poller. (in development)

## Docs

| Where | What |
|---|---|
| [bot/README.md](bot/README.md) | The whole system end to end — setup, the loop, usage, configuration |
| [docs/web-app.md](docs/web-app.md) | Modules 1 + 2 in depth — stack, workflow, database commands |
| [bot/docs/bot.md](bot/docs/bot.md) | The bot in depth — design decisions, concurrency, what is not built |
| [bot/docs/integration.md](bot/docs/integration.md) | The two-table contract between bank and bot |
| [bot/docs/deploy.md](bot/docs/deploy.md) | Vercel + Neon + the bot's always-on host |
| [PHASE_CHECKLIST.md](PHASE_CHECKLIST.md) | Build phases 1–10, and what each delivered |

## Tests

```bash
npm run test && npm run lint && npm run typecheck   # modules 1 + 2
cd bot && python -m pytest && python -m ruff check . # module 3 — 183 tests
```

## License and medical disclaimer

Modules 1 and 2 are licensed under **PolyForm Noncommercial 1.0.0**; see [LICENSE](LICENSE).

This software is provided **AS IS**. It is not medical advice, not a substitute for
clinical judgment, and not clinically validated. It must not be used in a real clinical
environment without appropriate validation, security review, compliance review and
institutional authorization. No claim of regulatory approval or production readiness is
made.
