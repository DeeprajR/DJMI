"""FastAPI application factory."""

from __future__ import annotations

from aiogram import Bot
from fastapi import FastAPI

from app.api.routes import router


def create_app(bot: Bot) -> FastAPI:
    app = FastAPI(
        title="Blood Donor Bot -- blood bank API",
        version="0.1.0",
        description=(
            "Inbound API for the blood bank system. Demand originates here; the bot is a "
            "distribution channel and exposes nothing about patients."
        ),
    )
    # Routes send Telegram messages as a side effect of the bank's calls.
    app.state.bot = bot
    app.include_router(router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
