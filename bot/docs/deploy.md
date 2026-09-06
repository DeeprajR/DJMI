# Deploying to Vercel

Three pieces, three places:

| Piece | Runs on | Reached at |
|---|---|---|
| Modules 1 + 2 — hospital + blood bank (Next.js) | **Vercel** | `https://<project>.vercel.app` |
| Database | **Neon** (already provisioned, `neondb`) | private |
| Module 3 — the Telegram bot (Python) | **Render** — one free web service from `bot/` | a public `/healthz` URL; everything else is long polling and Neon |

The bot has no public surface in this setup: the bank hands it work by writing rows,
and Telegram is reached by long polling. It just needs the database URL.

No custom domain for now. Vercel's default `*.vercel.app` hostname comes with HTTPS and
needs no DNS work; a domain can be added later under *Settings → Domains* without
touching the code.

## 1. The code is on GitHub

The Module 2 work is pushed as branch `module-2-blood-bank` on `DeeprajR/DJMI`
(commit `a3564ae`). `.env` is untracked from that commit onward. If an older commit on
`dev` still contains the committed `.env`, treat the `SESSION_SECRET` in it as public —
Vercel gets a fresh one below anyway.

## 2. Create the Vercel project

1. vercel.com → **Add New → Project** → import `DeeprajR/DJMI`.
2. **Production branch**: `module-2-blood-bank` (or `dev` after merging). Framework is
   detected as Next.js; leave build settings default.
3. **Environment variables** (Production):

| Name | Value |
|---|---|
| `DATABASE_URL` | the Neon **pooler** URL (`…-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require`) |
| `SESSION_SECRET` | 48+ random characters — `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `RFID_READER_TOKEN` | 32+ random characters; the reader will send this in `X-Reader-Token` |
| `NEXT_PUBLIC_BOT_USERNAME` | `blood_donor_people_bot` |
| `SEAL_STORAGE_DIR` | `/tmp/blood-request/seals` (see caveat) |

4. **Deploy.** First build takes ~2 minutes. The project URL is shown on the
   deployment page — every page lives under it: `/sign-in`, `/dashboard`, `/bank`,
   `/admin`, and the API under `/api/*`, including the reader's
   `POST https://<project>.vercel.app/api/bank/bags/scan`.

**Caveat — doctor seal images.** Module 1 stores uploaded seals on local disk. On
Vercel that disk is per-instance and wiped on every deploy, so a seal uploaded today can
be gone tomorrow. Everything else is fine. Before doctors rely on seals in production,
`src/lib/storage/seal.ts` needs an object store (Vercel Blob is the least work). Not a
blocker for the pilot.

## 3. The accounts already exist on Neon

| Role | Email | Password |
|---|---|---|
| Hospital admin | `admin@example.com` | `<rotate — never commit>` |
| Blood bank | `bank@hospital.local` | `<rotate — never commit>` |
| Doctor (test) | `doctor@hospital.local` | `<rotate — never commit>` |

Change all three before real users touch it: admin → `/admin` for doctors; the bank
account via `npm run seed:bank -- --email … --password …` against the Neon URL.

## 4. Run the bot on Render's free tier

The bot is a long-running process and cannot live on Vercel. It runs on Render as a **web
service on the free plan** — no credit card, 750 instance-hours per calendar month, which
covers one service running continuously (a month is about 730 hours). Render has no free
*background worker* tier, which is why this is a web service: the bot already runs a
FastAPI app in the same event loop as the poller, so it has a port to bind and `/healthz`
to answer on.

[`render.yaml`](../../render.yaml) at the repo root declares it. In the dashboard:
**New → Blueprint**, connect `DeeprajR/DJMI`, pick the branch. Render reads
`rootDir: bot`, builds with `pip install -e .` and starts `python -m app.main`.

Set the three secrets in the dashboard — they are `sync: false` so they never enter the repo:

| Name | Value |
|---|---|
| `BOT_TOKEN` | from @BotFather |
| `BOT_USERNAME` | the bot's username, no `@` |
| `DATABASE_URL` | the Neon **direct** endpoint, `postgresql+asyncpg://…/neondb?ssl=require` |

Note the two different Neon URLs: Vercel uses the **pooler** host with `sslmode=require`,
the bot uses the **direct** host with `+asyncpg` and `ssl=require`. Same database — the
bot's asyncpg driver does not accept the pooler's `channel_binding` parameter.

### The spin-down, and why it needs a pinger

**A free Render web service spins down after 15 minutes with no inbound HTTP request.** A
spun-down bot is not polling Telegram and not running the wave ticker, so donors go
unnotified. Render's own health checks do not count as traffic; only external requests do.

Point a free uptime monitor — [UptimeRobot](https://uptimerobot.com) or
[cron-job.org](https://cron-job.org) — at `https://<service>.onrender.com/healthz` every
**5 minutes**. That is the whole fix, and it is what makes the free plan viable here.

What a gap actually costs you, if the pinger fails: Telegram retains undelivered updates
for 24 hours, so donor taps queue and are processed on wake rather than being lost. The
wave ticker, though, simply does not run while the service is down — a request raised
during a gap waits for the next tick after wake-up. Cold start is roughly a minute.

If the pilot ever depends on the bot being up to the minute, the $7/month Starter plan
removes the spin-down entirely, and nothing about the deployment changes but the plan.

### Why `BLOOD_BANK_SECRETS` is left unset

A web service has a public URL, which means the bot's inbound blood-bank API is reachable
from the internet. With `BANK_SYNC_ENABLED=true` the bank hands over work by writing rows
to Neon, so that API is unused — and leaving `BLOOD_BANK_SECRETS` unset makes the bot
reject every signed request. Set it only if an external bank genuinely calls over HTTP,
and then to a strong random secret per bank; never to the placeholder in `.env.example`,
which is published in this repository.

A healthy start in the Render logs looks like:

```
token OK, polling as @<your bot>
starting bot, API on 0.0.0.0:10000
aiogram.dispatcher: Run polling for bot @<your bot>
```

The port is Render's — `app/config.py` reads `PORT` when `API_PORT` is not set.

Only **one** copy of the bot may run at a time. Stop any local `python -m app.main` before
deploying, or Telegram will drop one of the two with "terminated by other getUpdates
request".

### Alternative: any Linux box

```bash
git clone https://github.com/DeeprajR/DJMI && cd DJMI/bot
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # BOT_TOKEN, BOT_USERNAME, DATABASE_URL, DB_SCHEMA=donor_bot
```

`/etc/systemd/system/blood-bot.service`:

```ini
[Unit]
Description=Blood donor Telegram bot
After=network-online.target

[Service]
WorkingDirectory=/opt/DJMI/bot
ExecStart=/opt/DJMI/bot/.venv/bin/python -m app.main
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now blood-bot
journalctl -u blood-bot -f
```

## 5. Check it end to end

1. `https://<project>.vercel.app/sign-in` as the doctor → create a patient, admission, request → submit.
2. Sign out → sign in as the bank → `/bank/requests` → decide (partial, recruit donors).
3. Within a minute the bot imports the demand; volunteer admins get the card and share text.
4. A donor accepts → appears on `/bank/demand` → mark **Donated** → the bot thanks them.

## Rotating the Neon password

The connection string was pasted into a chat once. To rotate: Neon console → Roles →
`neondb_owner` → *Reset password*, then update `DATABASE_URL` in Vercel (redeploy) and in
the bot's `.env` (restart). Nothing else stores it.
