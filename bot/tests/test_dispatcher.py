"""End-to-end dispatcher wiring.

Everything else tests handler functions directly. These feed a real ``Update`` through
the real dispatcher, so they cover the layer in between -- router registration, the
command filters, both middlewares and FSM state -- which is exactly the layer that fails
silently: the bot polls happily and simply never answers.

Telegram is replaced by a mock session that records outgoing calls.
"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User

from app.bot.factory import create_dispatcher
from app.bot.states import OnbCB, Onboarding
from app.bot.storage import SqlAlchemyStorage, clear_all
from app.models import Donor

USER_ID = 555001


class MockSession(BaseSession):
    """Records outbound API calls instead of reaching Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[SendMessage] = []
        self.edited: list[EditMessageText] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - never used here
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            self.sent.append(method)
            return Message(
                message_id=len(self.sent),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if isinstance(method, EditMessageText):
            self.edited.append(method)
            return Message(
                message_id=method.message_id,
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        return True


@pytest_asyncio.fixture
async def wired(session):
    """A dispatcher with the real routers and middlewares, and a mocked Telegram.

    ``create_dispatcher`` is cached (one per process, since routers are singletons), so
    the FSM store is emptied here to keep tests independent of each other.
    """
    mock = MockSession()
    bot = Bot(token="8345644821:AAtest", session=mock)
    dispatcher = create_dispatcher()
    await clear_all()
    yield dispatcher, bot, mock
    await clear_all()
    await bot.session.close()


def message(text: str, user_id: int = USER_ID, update_id: int = 1) -> Update:
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id, date=datetime.now(), chat=chat, from_user=user, text=text
        ),
    )


def contact_message(
    user_id: int = USER_ID, update_id: int = 2, contact_user_id: int | None = -1
) -> Update:
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            contact=Contact(
                phone_number="+919847012345",
                first_name="Test",
                user_id=user_id if contact_user_id == -1 else contact_user_id,
            ),
        ),
    )


# --------------------------------------------------------------------------------------


async def test_start_is_answered(wired):
    """The check that would have caught a broken router: does /start reply at all?"""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))

    assert len(mock.sent) == 2, "expected a welcome and a contact prompt"
    assert "Welcome" in mock.sent[0].text


async def test_start_offers_the_contact_button(wired):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))

    keyboard = mock.sent[1].reply_markup
    button = keyboard.keyboard[0][0]
    assert button.request_contact is True, "the phone must come from Telegram, not typing"


async def test_deep_link_start_uses_the_request_wording(wired):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start req_ABCD2345"))

    assert "Someone nearby needs blood" in mock.sent[0].text


async def test_a_malformed_payload_falls_back_to_normal_start(wired):
    """`1` is not in the id alphabet, so this is not a request link."""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start req_ABCD1234"))

    assert "Welcome" in mock.sent[0].text


async def test_the_flow_advances_to_the_name_step(wired, session):
    """/start then a shared contact should ask for a name -- proves FSM state persists."""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))
    mock.sent.clear()
    await dispatcher.feed_update(bot, contact_message())

    assert len(mock.sent) == 1
    assert "call you" in mock.sent[0].text


async def test_state_is_set_after_start(wired):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))

    from aiogram.fsm.storage.base import StorageKey

    key = StorageKey(bot_id=bot.id, chat_id=USER_ID, user_id=USER_ID)
    assert await dispatcher.storage.get_state(key) == Onboarding.contact.state


async def test_two_users_starting_do_not_share_state(wired):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start", user_id=601, update_id=10))
    await dispatcher.feed_update(bot, message("/start", user_id=602, update_id=11))

    recipients = [m.chat_id for m in mock.sent]
    assert recipients.count(601) == 2
    assert recipients.count(602) == 2


async def test_a_registered_donor_is_not_asked_to_register_again(wired, session):
    dispatcher, bot, mock = wired
    from tests.conftest import make_donor

    session.add(make_donor(USER_ID))
    await session.commit()

    await dispatcher.feed_update(bot, message("/start"))

    assert len(mock.sent) == 1
    assert "already registered" in mock.sent[0].text.lower()


async def test_the_session_middleware_commits(wired, session):
    """A donor row must survive the update that created it."""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))
    await dispatcher.feed_update(bot, contact_message())

    # Onboarding deliberately writes no donor row until consent, so nothing yet...
    assert await session.get(Donor, USER_ID) is None
    # ...but the event log entry from /start was committed by the middleware.
    from sqlalchemy import func, select

    from app.models import EventLog

    count = await session.scalar(
        select(func.count()).select_from(EventLog).where(EventLog.event == "onboarding.started")
    )
    assert count == 1


@pytest.mark.parametrize("text", ["hello", "/help", "random chatter"])
async def test_unknown_input_does_not_crash_the_dispatcher(wired, text):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message(text))  # must not raise


# --------------------------------------------------------------------------------------
# Regressions: the onboarding loop that made the bot look broken
# --------------------------------------------------------------------------------------


async def test_typing_the_number_does_not_repeat_the_same_prompt(wired):
    """Repeating the identical ask reads as a loop. Explain the button instead."""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))
    first_ask = mock.sent[-1].text
    mock.sent.clear()

    await dispatcher.feed_update(bot, message("+91 98470 12345", update_id=20))

    assert len(mock.sent) == 1
    reply = mock.sent[0].text
    assert reply != first_ask, "the bot repeated itself verbatim"
    assert "button" in reply.lower()
    assert mock.sent[0].reply_markup is not None, "the keyboard must be offered again"


async def test_a_contact_is_accepted_even_with_no_state(wired):
    """After a restart the keyboard is still in the chat; the tap must still work."""
    dispatcher, bot, mock = wired
    await clear_all()  # as if the process had just restarted

    await dispatcher.feed_update(bot, contact_message(update_id=21))

    assert len(mock.sent) == 1, "a stateless contact tap was ignored"
    assert "call you" in mock.sent[0].text


async def test_onboarding_survives_a_restart(wired):
    """State is in the database, so a fresh storage object sees the same progress."""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))
    await dispatcher.feed_update(bot, contact_message())

    from aiogram.fsm.storage.base import StorageKey

    key = StorageKey(bot_id=bot.id, chat_id=USER_ID, user_id=USER_ID)
    reborn = SqlAlchemyStorage()
    assert await reborn.get_state(key) == Onboarding.name.state
    assert (await reborn.get_data(key))["phone"] == "+919847012345"


async def test_someone_elses_contact_is_refused_with_the_keyboard(wired):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))
    mock.sent.clear()

    await dispatcher.feed_update(bot, contact_message(update_id=22, contact_user_id=999999))

    assert "someone else" in mock.sent[0].text.lower()
    assert mock.sent[0].reply_markup is not None


async def test_a_contact_without_a_linked_account_is_refused(wired):
    """A contact picked from the address book has no user_id and cannot be verified."""
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("/start"))
    mock.sent.clear()

    await dispatcher.feed_update(bot, contact_message(update_id=23, contact_user_id=None))

    assert "someone else" in mock.sent[0].text.lower()


async def test_a_registered_donor_sharing_a_contact_is_not_re_onboarded(wired, session):
    from tests.conftest import make_donor

    dispatcher, bot, mock = wired
    session.add(make_donor(USER_ID))
    await session.commit()

    await dispatcher.feed_update(bot, contact_message(update_id=24))

    assert "already registered" in mock.sent[0].text.lower()


# --------------------------------------------------------------------------------------
# Never silent
# --------------------------------------------------------------------------------------


async def test_unknown_text_gets_a_hint_not_silence(wired):
    dispatcher, bot, mock = wired
    await dispatcher.feed_update(bot, message("hello there", update_id=30))

    assert len(mock.sent) == 1
    assert "/start" in mock.sent[0].text


async def test_a_registered_donor_typing_gets_a_reassurance(wired, session):
    from tests.conftest import make_donor

    dispatcher, bot, mock = wired
    session.add(make_donor(USER_ID))
    await session.commit()

    await dispatcher.feed_update(bot, message("hello?", update_id=31))

    assert "registered" in mock.sent[0].text.lower()


async def test_a_photo_gets_a_reply(wired):
    from aiogram.types import PhotoSize

    dispatcher, bot, mock = wired
    user = User(id=USER_ID, is_bot=False, first_name="Test")
    chat = Chat(id=USER_ID, type="private")
    update = Update(
        update_id=32,
        message=Message(
            message_id=32,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            photo=[PhotoSize(file_id="x", file_unique_id="y", width=1, height=1)],
        ),
    )
    await dispatcher.feed_update(bot, update)

    assert len(mock.sent) == 1
    assert "/start" in mock.sent[0].text


# --------------------------------------------------------------------------------------
# The whole registration, buttons and all, through the real dispatcher
# --------------------------------------------------------------------------------------


def tap(field: str, value: str, update_id: int, user_id: int = USER_ID) -> Update:
    """A button press on the onboarding keyboard."""
    user = User(id=user_id, is_bot=False, first_name="Test")
    chat = Chat(id=user_id, type="private")
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=user,
            chat_instance="ci",
            data=OnbCB(field=field, value=value).pack(),
            message=Message(message_id=500, date=datetime.now(), chat=chat, text="?"),
        ),
    )


async def _register(dispatcher, bot, *, consent: str = "1") -> None:
    """Every step a donor takes, in order. Kozhikode is index 10 in the district list."""
    steps = [
        message("/start", update_id=100),
        contact_message(update_id=101),
        message("Deepraj", update_id=102),
        tap("dob_year", "2001", 103),
        tap("dob_month", "12", 104),
        tap("dob_day", "19", 105),
        tap("sex", "M", 106),
        tap("blood_group", "B+", 107),
        tap("district", "10", 108),
        tap("city", "0", 109),
        tap("donated_before", "1", 110),
        tap("last_year", "2026", 111),
        tap("last_month", "2", 112),
        tap("last_day", "10", 113),
        tap("consent", consent, 114),
    ]
    for update in steps:
        await dispatcher.feed_update(bot, update)


async def test_full_registration_creates_the_donor(wired, session):
    """The consent tap writes the donor row and then clears FSM state -- in one
    transaction. With two SQLite connections that pair deadlocked and the bot froze on
    the very last question."""
    dispatcher, bot, mock = wired

    await _register(dispatcher, bot)

    donor = await session.get(Donor, USER_ID)
    assert donor is not None, "no donor row -- the consent handler did not complete"
    assert donor.is_registered is True
    assert donor.full_name == "Deepraj"
    assert donor.blood_group == "B+"
    assert donor.district == "Kozhikode"
    assert donor.city == "Kozhikode"
    assert donor.sex == "M"
    assert str(donor.dob) == "2001-12-19"
    assert str(donor.last_donation_date) == "2026-02-10"
    assert donor.phone == "+919847012345"
    assert donor.consent_at is not None


async def test_full_registration_clears_the_conversation(wired, session):
    from aiogram.fsm.storage.base import StorageKey

    dispatcher, bot, mock = wired
    await _register(dispatcher, bot)

    key = StorageKey(bot_id=bot.id, chat_id=USER_ID, user_id=USER_ID)
    assert await SqlAlchemyStorage().get_state(key) is None
    assert await SqlAlchemyStorage().get_data(key) == {}


async def test_full_registration_ends_with_a_confirmation(wired):
    dispatcher, bot, mock = wired
    await _register(dispatcher, bot)

    final = mock.edited[-1].text
    assert "registered" in final.lower()
    assert "Deepraj" in final and "B+" in final and "Kozhikode" in final


async def test_declining_consent_stores_nothing(wired, session):
    dispatcher, bot, mock = wired
    await _register(dispatcher, bot, consent="0")

    assert await session.get(Donor, USER_ID) is None
    assert "not send you any requests" in mock.edited[-1].text.lower()


async def test_a_second_consent_tap_is_harmless(wired, session):
    """Telegram redelivers taps; the second one must not crash or duplicate."""
    dispatcher, bot, mock = wired
    await _register(dispatcher, bot)
    await dispatcher.feed_update(bot, tap("consent", "1", 115))

    donor = await session.get(Donor, USER_ID)
    assert donor is not None and donor.is_registered
