# Module 3 — the Telegram donor bot.
#
# Built from bot/ as its own context; Modules 1 and 2 at the repo root are not
# part of this image. The bot opens no inbound port on Fly: it reaches Telegram
# by long polling and takes work from rows in the shared Neon database.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# pyproject and the package together, because the dependency list is declared in
# pyproject and `pip install -e .` needs app/ on disk to resolve it.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e .

# Operator tools — add_admin.py, doctor.py, inspect_db.py — usable via `fly ssh console`.
COPY scripts ./scripts

# Fail fast and legibly if the image was built without the token reaching it.
CMD ["python", "-m", "app.main"]
