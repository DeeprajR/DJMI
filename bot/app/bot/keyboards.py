"""Inline keyboards.

The PRD's onboarding promise is that a donor types nothing but their name, so every
other field -- including both dates -- is a button grid built here.
"""

from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.states import OnbCB, QuizCB, ReqCB
from app.config import settings
from app.enums import BloodGroup, Sex
from app.i18n import t, tl

YEARS_PER_PAGE = 24


def contact_request(lang: str) -> ReplyKeyboardMarkup:
    """The one reply keyboard we use -- Telegram only shares a verified number here."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("onboarding.contact_button", lang), request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def _grid(builder: InlineKeyboardBuilder, width: int) -> InlineKeyboardMarkup:
    builder.adjust(width)
    return builder.as_markup()


# --------------------------------------------------------------------------------------
# Onboarding
# --------------------------------------------------------------------------------------


def dob_years(lang: str, page: int = 0) -> InlineKeyboardMarkup:
    """Birth years covering the eligible age range, newest first."""
    today = date.today()
    newest = today.year - settings.min_age
    oldest = today.year - settings.max_age
    years = list(range(newest, oldest - 1, -1))

    pages = max(1, -(-len(years) // YEARS_PER_PAGE))
    page = max(0, min(page, pages - 1))
    chunk = years[page * YEARS_PER_PAGE : (page + 1) * YEARS_PER_PAGE]

    builder = InlineKeyboardBuilder()
    for year in chunk:
        builder.button(text=str(year), callback_data=OnbCB(field="dob_year", value=str(year)))
    builder.adjust(4)

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="◀ Newer", callback_data=OnbCB(field="dob_page", value="x", page=page - 1))
    if page < pages - 1:
        nav.button(text="Older ▶", callback_data=OnbCB(field="dob_page", value="x", page=page + 1))
    if nav.buttons:
        builder.attach(nav)
    return builder.as_markup()


def months(lang: str, field: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index in range(1, 13):
        builder.button(
            text=calendar.month_abbr[index],
            callback_data=OnbCB(field=field, value=str(index)),
        )
    return _grid(builder, 4)


def days(lang: str, field: str, year: int, month: int) -> InlineKeyboardMarkup:
    """Only the days that exist in this month -- no invalid dates to validate."""
    last = calendar.monthrange(year, month)[1]
    builder = InlineKeyboardBuilder()
    for day in range(1, last + 1):
        builder.button(text=str(day), callback_data=OnbCB(field=field, value=str(day)))
    return _grid(builder, 7)


def sexes(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("onboarding.sex_male", lang), callback_data=OnbCB(field="sex", value=Sex.MALE)
    )
    builder.button(
        text=t("onboarding.sex_female", lang), callback_data=OnbCB(field="sex", value=Sex.FEMALE)
    )
    builder.button(
        text=t("onboarding.sex_other", lang), callback_data=OnbCB(field="sex", value=Sex.OTHER)
    )
    return _grid(builder, 3)


def blood_groups(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in (
        BloodGroup.A_POS,
        BloodGroup.A_NEG,
        BloodGroup.B_POS,
        BloodGroup.B_NEG,
        BloodGroup.O_POS,
        BloodGroup.O_NEG,
        BloodGroup.AB_POS,
        BloodGroup.AB_NEG,
    ):
        builder.button(
            text=group.value, callback_data=OnbCB(field="blood_group", value=group.value)
        )
    builder.adjust(2)
    unknown = InlineKeyboardBuilder()
    unknown.button(
        text=t("common.dont_know", lang),
        callback_data=OnbCB(field="blood_group", value=BloodGroup.UNKNOWN),
    )
    builder.attach(unknown)
    return builder.as_markup()


def districts(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, name in enumerate(tl("regions.districts", lang)):
        # Index, not name: district names blow past the 64-byte callback_data cap.
        builder.button(text=name, callback_data=OnbCB(field="district", value=str(index)))
    return _grid(builder, 2)


def cities(lang: str, district: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, name in enumerate(tl(f"regions.cities.{district}", lang)):
        builder.button(text=name, callback_data=OnbCB(field="city", value=str(index)))
    builder.adjust(2)
    other = InlineKeyboardBuilder()
    other.button(
        text=t("onboarding.city_other", lang, district=district),
        callback_data=OnbCB(field="city", value="-1"),
    )
    builder.attach(other)
    return builder.as_markup()


def yes_no(lang: str, field: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("common.yes", lang), callback_data=OnbCB(field=field, value="1"))
    builder.button(text=t("common.no", lang), callback_data=OnbCB(field=field, value="0"))
    return _grid(builder, 2)


def consent(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("onboarding.consent_yes", lang), callback_data=OnbCB(field="consent", value="1")
    )
    builder.button(
        text=t("onboarding.consent_no", lang), callback_data=OnbCB(field="consent", value="0")
    )
    return _grid(builder, 1)


def last_donation_years(lang: str) -> InlineKeyboardMarkup:
    """Recent years only -- anything older has long cleared the cooldown."""
    this_year = date.today().year
    builder = InlineKeyboardBuilder()
    for year in range(this_year, this_year - 3, -1):
        builder.button(text=str(year), callback_data=OnbCB(field="last_year", value=str(year)))
    builder.button(
        text=t("common.dont_know", lang), callback_data=OnbCB(field="last_year", value="0")
    )
    return _grid(builder, 2)


# --------------------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------------------


def request_card(lang: str, public_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("request.accept", lang), callback_data=ReqCB(action="acc", pid=public_id))
    builder.button(
        text=t("request.decline", lang), callback_data=ReqCB(action="dec", pid=public_id)
    )
    return _grid(builder, 1)


def quiz(lang: str, public_id: str, index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("common.yes", lang), callback_data=QuizCB(pid=public_id, idx=index, ans=1)
    )
    builder.button(text=t("common.no", lang), callback_data=QuizCB(pid=public_id, idx=index, ans=0))
    return _grid(builder, 2)
