# Deploying to Vercel

Three pieces, three places:

| Piece | Runs on | Reached at |
|---|---|---|
| Modules 1 + 2 — hospital + blood bank (Next.js) | **Vercel** | `https://<project>.vercel.app` |
| Database | **Neon** (already provisioned, `neondb`) | private |
| Module 3 — the Telegram bot (Python) | **a normal process** — this PC for now, a small VPS later | nothing public; it polls Telegram and talks to Neon |

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

## 4. Run the bot

The bot is a long-running process and cannot live on Vercel. Its `.env` already points at
Neon (direct endpoint, `ssl=require`, `DB_SCHEMA=donor_bot`, `BANK_SYNC_ENABLED=true`).

**For now, on this PC:**

```powershell
python -m app.main
```

**For the pilot, on any small Linux box** (Ubuntu, 512 MB is plenty):

```bash
git clone <bot repo> && cd bloody-project
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # BOT_TOKEN, BOT_USERNAME, DATABASE_URL (Neon direct, ssl=require), DB_SCHEMA=donor_bot, BANK_SYNC_ENABLED=true
```

`/etc/systemd/system/blood-bot.service`:

```ini
[Unit]
Description=Blood donor Telegram bot
After=network-online.target

[Service]
WorkingDirectory=/opt/bloody-project
ExecStart=/opt/bloody-project/.venv/bin/python -m app.main
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

Only **one** copy of the bot may run at a time — Telegram rejects a second poller. Stop
the PC copy before starting the server one.

## 5. Check it end to end

1. `https://<project>.vercel.app/sign-in` as the doctor → create a patient, admission, request → submit.
2. Sign out → sign in as the bank → `/bank/requests` → decide (partial, recruit donors).
3. Within a minute the bot imports the demand; volunteer admins get the card and share text.
4. A donor accepts → appears on `/bank/demand` → mark **Donated** → the bot thanks them.

## Rotating the Neon password

The connection string was pasted into a chat once. To rotate: Neon console → Roles →
`neondb_owner` → *Reset password*, then update `DATABASE_URL` in Vercel (redeploy) and in
the bot's `.env` (restart). Nothing else stores it.
