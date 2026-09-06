"""FSM states and callback-data schemas.

Callback payloads stay short on purpose: Telegram caps ``callback_data`` at 64 bytes, so
requests travel as their 8-character public id rather than a database key.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    """PRD 7.3. Every step is buttons except ``name``."""

    contact = State()
    name = State()
    dob_year = State()
    dob_month = State()
    dob_day = State()
    sex = State()
    blood_group = State()
    district = State()
    city = State()
    donated_before = State()
    last_year = State()
    last_month = State()
    last_day = State()
    consent = State()


class OnbCB(CallbackData, prefix="o"):
    """A choice made during onboarding. ``page`` drives the year picker."""

    field: str
    value: str
    page: int = 0


class ReqCB(CallbackData, prefix="r"):
    """Accept / decline on a request card. ``pid`` is the request public id."""

    action: str  # acc | dec | open
    pid: str


class QuizCB(CallbackData, prefix="q"):
    """One questionnaire answer. ``idx`` guards against out-of-order taps."""

    pid: str
    idx: int
    ans: int  # 1 = yes, 0 = no
