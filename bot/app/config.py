"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = "000:test"
    bot_username: str = "blood_donor_bot"

    # Telegram transport. Worst case per call is roughly retries x timeout, so keep the
    # product bounded -- a donor waiting 90s is bad; one waiting forever is worse.
    telegram_timeout: float = 30.0
    telegram_retries: int = 3
    telegram_retry_delay: float = 1.0

    # Database. On Postgres the bot keeps its tables in their own schema so they cannot
    # collide with the hospital app's (both have a `blood_requests`). Leave empty on SQLite.
    database_url: str = "sqlite+aiosqlite:///./blood.db"
    db_schema: str | None = None

    # Shared-database integration with the blood bank (Module 2). When enabled, the
    # ticker imports open rows from public.donor_demand and reports progress back.
    bank_sync_enabled: bool = False
    #: Identifier recorded on requests that came from the shared table.
    bank_id: str = "hospital_bank"

    # Inbound API
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    blood_bank_secrets: dict[str, str] = Field(default_factory=lambda: {"demo_bank": "dev-secret"})

    # Distribution (PRD 7.5)
    wave_size: int = 20
    wave_interval_minutes: int = 30
    tick_seconds: int = 60

    # Eligibility (PRD 7.4)
    cooldown_days_male: int = 90
    cooldown_days_female: int = 120
    min_age: int = 18
    max_age: int = 65

    # Misc
    locale: str = "en"
    #: Everything is stored in UTC; donors are shown local time.
    display_timezone: str = "Asia/Kolkata"
    support_contact: str = "@support"
    log_level: str = "INFO"

    @field_validator("db_schema", mode="before")
    @classmethod
    def _empty_schema_is_none(cls, v: object) -> object:
        # DB_SCHEMA= (empty) in .env means "no schema", not a schema named "".
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("blood_bank_secrets", mode="before")
    @classmethod
    def _parse_secrets(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v

    def deep_link(self, public_id: str) -> str:
        """t.me deep link for a request. Telegram caps `start` payload at 64 chars (PRD 12)."""
        payload = f"req_{public_id}"
        assert len(payload) <= 64, "start payload exceeds Telegram's 64-char limit"
        return f"https://t.me/{self.bot_username}?start={payload}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
