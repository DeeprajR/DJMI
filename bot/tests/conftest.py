"""Test fixtures.

Environment is set before ``app`` is imported, because ``app.config.settings`` is built
at import time and the engine is created from it.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_blood.db"
os.environ["BOT_TOKEN"] = "123456:test-token"
os.environ["BOT_USERNAME"] = "test_blood_bot"
os.environ["BLOOD_BANK_SECRETS"] = '{"demo_bank": "test-secret", "other_bank": "other-secret"}'
os.environ["WAVE_SIZE"] = "3"
# The developer's .env may point at Postgres with a schema and bank sync on; tests run
# on SQLite with neither, whatever .env says.
os.environ["DB_SCHEMA"] = ""
os.environ["BANK_SYNC_ENABLED"] = "false"

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.enums import BloodGroup, Sex  # noqa: E402
from app.models import Base, BloodRequest, Donor  # noqa: E402


@pytest_asyncio.fixture
async def session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        yield s


@pytest.fixture
def today() -> date:
    return date.today()


def make_donor(
    user_id: int,
    *,
    blood_group: str = BloodGroup.O_POS,
    district: str = "Ernakulam",
    city: str = "Kochi",
    sex: str = Sex.MALE,
    age: int = 30,
    last_donation: date | None = None,
    registered: bool = True,
    opted_out: bool = False,
    snoozed_until: date | None = None,
) -> Donor:
    return Donor(
        telegram_user_id=user_id,
        phone=f"+9199000{user_id:05d}",
        full_name=f"Donor {user_id}",
        dob=date.today().replace(year=date.today().year - age),
        sex=sex,
        blood_group=blood_group,
        district=district,
        city=city,
        last_donation_date=last_donation,
        is_registered=registered,
        opted_out=opted_out,
        snoozed_until=snoozed_until,
        consent_at=datetime.now(UTC),
    )


def make_request(
    *,
    public_id: str = "TESTREQ1",
    external_id: str = "ext-1",
    blood_group: str = BloodGroup.O_POS,
    units: int = 1,
    district: str = "Ernakulam",
    city: str = "Kochi",
    hours_ahead: int = 6,
    exact_match: bool = False,
) -> BloodRequest:
    return BloodRequest(
        public_id=public_id,
        blood_bank_id="demo_bank",
        external_id=external_id,
        blood_group=blood_group,
        exact_match=exact_match,
        units_needed=units,
        hospital_name="General Hospital",
        hospital_address="MG Road, Kochi",
        district=district,
        city=city,
        needed_by=datetime.now(UTC) + timedelta(hours=hours_ahead),
    )


class FakeBot:
    """Records outbound messages instead of calling Telegram."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self._next_id = 100

    async def send_message(self, chat_id, text, reply_markup=None, **_):
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text})
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=self._next_id)

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None, **_):
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text})
        return True


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


class StubMessage:
    def __init__(self, bot, chat_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.answers: list[str] = []
        self.edits: list[str] = []

    async def answer(self, text, reply_markup=None, **_):
        self.answers.append(text)
        return SimpleNamespace(chat=SimpleNamespace(id=self.chat_id), message_id=999)

    async def edit_text(self, text, reply_markup=None, **_):
        self.edits.append(text)

    async def edit_reply_markup(self, reply_markup=None, **_):
        return None


class StubQuery:
    def __init__(self, bot, donor_id: int) -> None:
        self.bot = bot
        self.from_user = SimpleNamespace(id=donor_id)
        self.message = StubMessage(bot, donor_id)
        self.alerts: list[str | None] = []

    async def answer(self, text=None, show_alert=False, **_):
        self.alerts.append(text)
