# How to run it

A walkthrough from a fresh clone to watching a real request land in your own Telegram.
Commands are PowerShell (the project's default shell on Windows); on macOS/Linux the only
differences are `cp` instead of `Copy-Item` and forward slashes.

Everything here has been run against this codebase — the outputs below are real.

---

## 1. Prerequisites

- **Python 3.11+** (developed on 3.14)
- A **Telegram account**
- No database to install — it uses SQLite by default and creates the file itself

```powershell
python --version
```

---

## 2. Install

This project has a virtual environment at `.venv`. **Everything is already installed in
it** — you only need the commands below if you are setting up from scratch or something
looks broken.

```powershell
python -m venv .venv                          # only if .venv does not exist yet
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Note the path form: **`.\.venv\Scripts\python.exe`** — backslashes, with a leading `.\`.
If you copy an interpreter path out of the VS Code status bar you get `/c:/Users/...`,
which is a URI rather than a Windows path; PowerShell rejects it with
`is not recognized as the name of a cmdlet`.

Note also that it is `-m pip`, once. `-m python -m pip` is not a thing.

### Two ways to run commands

**Either** activate the environment once per terminal, then use plain `python`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Your prompt gains a `(.venv)` prefix. This is the more comfortable option.

**Or** skip activation and call the interpreter directly every time:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The rest of this guide writes plain `python`, which assumes you activated. If you did
not, substitute `.\.venv\Scripts\python.exe` everywhere.

> If activation fails with **"running scripts is disabled on this system"**, PowerShell's
> execution policy is blocking it. Allow local scripts for your user:
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
>
> Or use the direct-call form above, which never needs activation.

### Confirm it works

```powershell
python -m pytest -q
```

Expect `183 passed`. **If the tests pass, the whole engine is proven** — eligibility, the
compatibility matrix, wave fan-out, the screening gate, the last-unit guard and the blood
bank API all run without a Telegram token. You only need a token to see it in a chat.

You can check which interpreter you are on at any time:

```powershell
python -c "import sys; print(sys.executable)"
```

```
C:\Users\dr\Desktop\bloody-project\.venv\Scripts\python.exe
```

If that prints `C:\Python314\python.exe` instead, you are on the global interpreter
rather than the venv.

---

## 3. Get a bot token

Skip this if `.env` already has a working `BOT_TOKEN` (this project's does).

1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Give it a display name (e.g. `BloodBot`) and a username ending in `bot`
   (e.g. `blood_donor_people_bot`)
4. BotFather replies with a token like `8345644821:AAH...`

Keep the token out of git — `.env` is already in `.gitignore`.

---

## 4. Configure

```powershell
Copy-Item .env.example .env
```

Then edit `.env`. Only the first two lines matter to start:

```ini
BOT_TOKEN=8345644821:AAH...           # from BotFather
BOT_USERNAME=blood_donor_people_bot   # WITHOUT the @
```

> **`BOT_USERNAME` must match your bot exactly.** It is not used to connect — it builds
> the deep links that admins forward. A typo here fails silently: the bot runs fine and
> every forwarded link goes nowhere.

Check both at once:

```powershell
python -c "from app.config import settings; print(settings.deep_link('ABCD1234'))"
```

```
https://t.me/blood_donor_people_bot?start=req_ABCD1234
```

Open that link. If Telegram finds your bot, the username is right.

### Worth knowing while testing

| Setting | Default | Why you might change it |
|---|---|---|
| `WAVE_SIZE` | `20` | Set to `2` to watch several waves without seeding many donors |
| `WAVE_INTERVAL_MINUTES` | `30` | Set to `1` to see escalation in a minute instead of half an hour |
| `TICK_SECONDS` | `60` | How often due waves are checked. Leave alone |
| `BLOOD_BANK_SECRETS` | `{"demo_bank": "dev-secret-change-me"}` | The HMAC secret the mock client signs with. Must match what you pass to the API |

---

## 5. Start it

```powershell
python -m app.main
```

```
INFO  __main__: starting bot, API on 0.0.0.0:8080
INFO  aiogram.dispatcher: Start polling
INFO  Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
INFO  aiogram.dispatcher: Run polling for bot @blood_donor_people_bot id=8345644821 - 'BloodBot'
```

That last line is the one that matters — it means your token works and Telegram
recognises the bot. One process runs three things: the bot (long polling), the blood bank
API on `:8080`, and the ticker that escalates waves and expires requests.

> **`http://0.0.0.0:8080` is not a link you can open.** `0.0.0.0` is a *bind* address
> meaning "listen on every network interface"; it is not an address anything connects
> to. Reach the server at **`http://127.0.0.1:8080`** (or `http://localhost:8080`) from
> this machine, or at this machine's LAN IP from another device. The binding comes from
> `API_HOST` in `.env`, and `0.0.0.0` is the right default — `127.0.0.1` alone would
> refuse connections from anywhere but this machine.

`Ctrl+C` stops it. Leave it running and open a **second terminal** for everything below.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/healthz
```

```
status
------
ok
```

> In Windows PowerShell, **`curl` is an alias for `Invoke-WebRequest`**, not the real
> curl — it works but prints a large response object instead of the body. Use
> `Invoke-RestMethod` as above, or call real curl explicitly as **`curl.exe`**:
>
> ```powershell
> curl.exe -s http://127.0.0.1:8080/healthz
> ```
> ```json
> {"status":"ok"}
> ```

Interactive API docs, generated from the code: **http://127.0.0.1:8080/docs**
(you cannot call endpoints from that page — they need a signature; use the mock client).

---

## 6. Register yourself as a donor

In Telegram, open your bot and send `/start`.

It walks you through: share contact → type your name → date of birth (3 taps) → sex →
blood group → district → town → donated before? → consent. **Your name is the only thing
you type.**

Pick **Ernakulam** as the district if you want the examples below to reach you, and pick a
blood group that can donate to `O+` — that is `O+` or `O-`.

> The district list is Kerala's 14. To change it, edit `regions:` at the bottom of
> [app/locales/en.yml](../app/locales/en.yml).

---

## 7. Add a synthetic donor pool

Real donors are scarce in testing, and waves are the interesting part:

```powershell
python scripts/seed_donors.py --district Ernakulam --count 40
```

```
Added 40 seeded donors in Ernakulam (40 seeded donors in total).
```

Seeded donors get random blood groups, ages and last-donation dates, so eligibility and
wave ordering actually have something to chew on. They carry **negative Telegram ids**,
which real accounts never have — so they cannot collide with you, and they are trivial to
remove:

```powershell
python scripts/seed_donors.py --clear
```

**They cannot receive messages.** You will see this in the server log, and it is correct:

```
WARNING  app.bot.render: could not deliver card to -1000005: Bad Request: chat not found
INFO     app.distribution: request KQPTHURE wave 1: 0/3 donors reached
```

The wave logged the failure, dropped those link rows so a later wave can retry, and moved
on. Use seeded donors to exercise **who gets selected and in what order**; use your own
account to exercise **the messages**.

---

## 8. Raise a request

This is the blood bank's job, so it goes through the signed API. `scripts/mock_blood_bank.py`
is the stand-in:

```powershell
python scripts/mock_blood_bank.py create --group O+ --units 2
```

```
POST /v1/requests -> 201
{
  "public_id": "KQPTHURE",
  "status": "OPEN",
  "blood_group": "O+",
  "units_needed": 2,
  "confirmed_count": 0,
  "deep_link": "https://t.me/blood_donor_people_bot?start=req_KQPTHURE",
  "needed_by": "2026-09-06T02:35:13Z",
  "created": true
}

Forward this link:
  https://t.me/blood_donor_people_bot?start=req_KQPTHURE
```

If you registered in Ernakulam with a compatible group, **the card is already in your
chat.** Tap **✅ I can donate**, answer the questions, and you are confirmed with the
hospital, address and time.

Useful flags:

```powershell
python scripts/mock_blood_bank.py create --group A+ --units 1 --district Ernakulam --city Kochi
python scripts/mock_blood_bank.py create --group O- --units 3 --hours 2      # tighter deadline
python scripts/mock_blood_bank.py create --group B+ --slot-hours 3          # assign a slot
python scripts/mock_blood_bank.py create --group AB+ --exact-match          # no matrix
python scripts/mock_blood_bank.py create --group O+ --notes "Ask at the day-care counter"
python scripts/mock_blood_bank.py create --group O+ --external-id BB-001    # repeat to test idempotency
```

`--group` is the **patient's** group; the bot applies the compatibility matrix, so an `A+`
request also reaches `O+`, `O-` and `A-` donors.

---

## 9. The rest of the loop

```powershell
# Progress
python scripts/mock_blood_bank.py status KQPTHURE

# Who to expect at the counter (name + verified phone)
python scripts/mock_blood_bank.py donors KQPTHURE

# Record a collected donation -> updates cooldown, sends the thank-you
python scripts/mock_blood_bank.py complete KQPTHURE --telegram-id <your telegram id>

# Withdraw it -> clears the Accept button from every unanswered card
python scripts/mock_blood_bank.py close KQPTHURE --status CANCELLED --reason "patient stabilised"
```

Your Telegram id shows up in the `donors` output, and in `scripts/inspect_db.py`
([section 11](#11-look-inside-the-database)).

---

## 10. Watch waves escalate

Waves are the heart of PRD 7.5 and the default timings are too slow to watch. In `.env`:

```ini
WAVE_SIZE=2
WAVE_INTERVAL_MINUTES=1
```

Restart, seed 10 donors, create a request needing 5 units, and watch the log:

```
INFO  app.distribution: request X wave 1: 2/2 donors reached
INFO  app.distribution: request X wave 2: 2/2 donors reached
INFO  app.distribution: request X wave 3: 2/2 donors reached
```

Then confirm enough donors and the waves stop immediately — that is P0-5's acceptance
criterion. Put the values back afterwards.

---

## 11. Look inside the database

```powershell
python scripts/inspect_db.py
```

```
REQUESTS
--------
KQPTHURE  O+   OPEN      confirmed 0/2  completed 0  Kochi, Ernakulam  wave=1

REAL DONORS (seeded ones hidden)
--------------------------------
   884412299  Anitha R         O+      Kochi          last_donation=never

RESPONSES
---------
KQPTHURE   donor=884412299  CONFIRMED       wave=0 answers=6
```

This is the fastest way to answer *"why did nobody get notified?"* — check the donor's
blood group, city and flags against the request on one screen.

```powershell
python scripts/inspect_db.py --events        # every state transition, timestamped
python scripts/inspect_db.py --all-donors    # include the seeded pool
```

`--events` prints the `event_log` table, which is what the PRD's success metrics are
computed from.

## 12. Troubleshooting

| What you see | What it means |
|---|---|
| `TelegramUnauthorizedError: token is invalid` | `BOT_TOKEN` is wrong or still the placeholder. Re-copy it from BotFather |
| Bot starts, but a deep link opens the wrong bot / nothing | `BOT_USERNAME` does not match. It is the username **without `@`** |
| `could not deliver card to -1000005: chat not found` | Normal — a seeded donor. Not an error |
| `create` returns `401` | The secret in `BLOOD_BANK_SECRETS` differs from what the client signs with. Both read the same `.env`, so this usually means you passed `--secret` |
| `create` returns `422 needed_by is already past` | `--hours` too small, or your clock is off |
| Request created but **nobody** notified | No eligible donor. Check district spelling, blood-group compatibility, and that your own record is `is_registered` (finish `/start` through consent) |
| `Could not reach http://127.0.0.1:8080` | `python -m app.main` is not running in the other terminal |
| `[WinError 10048] address already in use` | Port 8080 is taken. Change `API_PORT` in `.env` |
| `UnicodeEncodeError: 'charmap'` when printing a card | Windows console encoding. Prefix with `$env:PYTHONIOENCODING="utf-8"` |
| `/start` does nothing | The bot process died. Check the first terminal |
| It keeps asking for your phone number | You are typing it. Tap the **📱 Share my number** button instead — Telegram sends a verified number, a typed one cannot be trusted. If the button is hidden, tap the keyboard icon in the message box |
| Sharing a contact does nothing | Fixed in this build: a contact is now accepted even with no state. If you are on an older copy, send `/start` first |
| Freezes on the consent question | Fixed in this build (an SQLite deadlock between the donor insert and clearing FSM state). Restart the bot; your answers are saved, so tapping **Yes, notify me** again completes registration |
| `'/c:/Users/.../python.exe' is not recognized` | That is a VS Code URI, not a path. Use `.\.venv\Scripts\python.exe` |
| `No module named python` | The command said `-m python -m pip`. It is just `-m pip` |
| `Activate.ps1 cannot be loaded, running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, or call `.\.venv\Scripts\python.exe` directly |
| Browser will not open `http://0.0.0.0:8080` | Expected — it is a bind address. Use `http://127.0.0.1:8080` |
| `ModuleNotFoundError: No module named 'aiogram'` | You are on the global interpreter, not the venv. Check with `python -c "import sys; print(sys.executable)"` |

---

## 13. Start over

```powershell
python scripts/seed_donors.py --clear   # remove synthetic donors, keep real ones
Remove-Item blood.db                    # wipe everything; recreated on next start
```

Deleting `blood.db` also deletes **you** — you will need to `/start` again.

---

## 14. Running with the blood bank dashboard (Modules 1 + 2)

Everything above uses SQLite and the mock HTTP client. The real deployment shares one
PostgreSQL with the hospital app. The full sequence — provisioning, migrations, the bank
account, and the end-to-end flow — is in [integration.md](integration.md). The short
version:

```powershell
python scripts/setup_shared_db.py postgresql://postgres:<password>@127.0.0.1:5432
# ...paste the printed lines into both .env files, then:
python scripts/add_admin.py <your telegram id> --name "You" --district Kozhikode
python -m app.main
```

With `BANK_SYNC_ENABLED=true` the ticker imports open `donor_demand` rows every
`TICK_SECONDS`; `scripts/mock_blood_bank.py` is no longer needed.

---

## 15. Before this runs for real

The defaults are development defaults. Do not point a pilot at them without:

- **A real `BLOOD_BANK_SECRETS` value**, generated per bank and shared out of band —
  `dev-secret-change-me` is exactly what it says
- **Postgres**, not SQLite: `DATABASE_URL=postgresql+asyncpg://user:pass@host/db`
- **Alembic migrations** — the schema is currently `create_all`, which cannot evolve a
  database that already holds donors
- **TLS in front of the API.** Signatures prove who sent a request; they do not hide it
- **The consent text reviewed by a lawyer** against the DPDP Act 2023 — the wording in
  `onboarding.ask_consent` was written by an engineer
- **A retention policy for `event_log`**, which grows without bound and holds
  health-adjacent data

For the blood bank's side of the integration, hand them
[docs/blood-bank-api.md](blood-bank-api.md).
