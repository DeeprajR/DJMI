"""Last-resort replies, so the bot is never silent.

Registered last. Anything that reached here matched no real handler -- a stray word, a
sticker, a tap on a keyboard from a conversation the server no longer knows about.
Silence in those cases is indistinguishable from the bot being down.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.i18n import t
from app.models import Donor

log = logging.getLogger(__name__)
router = Router(name="fallback")


@router.message(F.text)
async def unknown_text(message: Message, donor: Donor | None) -> None:
    lang = donor.language if donor else settings.locale
    key = "fallback.registered" if donor and donor.is_registered else "fallback.unregistered"
    await message.answer(t(key, lang, support=settings.support_contact))


@router.message()
async def unknown_message(message: Message, donor: Donor | None) -> None:
    """Photos, stickers, voice notes -- anything that is not text or a contact."""
    lang = donor.language if donor else settings.locale
    await message.answer(t("fallback.not_text", lang))


@router.callback_query()
async def stale_button(query: CallbackQuery, donor: Donor | None) -> None:
    """A button from a message the server no longer has state for."""
    lang = donor.language if donor else settings.locale
    log.info("stale callback %r from %s", query.data, query.from_user.id)
    await query.answer(t("fallback.stale_button", lang), show_alert=True)
