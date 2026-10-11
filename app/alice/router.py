from __future__ import annotations

from app.alice import session_store
from app.alice.models import AliceRequestBody
from app.alice.scenarios import add_booking, today_bookings
from app.dikidi.client import DikidiClient

WELCOME_TEXT = (
    "Скажите «добавь запись», чтобы записать клиента, "
    "или спросите, сколько записей на сегодня."
)

ADD_BOOKING_KEYWORDS = [
    "добавь запись", "добавить запись", "новая запись",
    "запиши клиента", "запись клиента", "добавь клиента",
]
TODAY_BOOKINGS_CONTEXT_WORDS = ["запис", "человек", "клиент"]


def handle(body: AliceRequestBody, dikidi: DikidiClient) -> tuple[str, dict]:
    session_id = body.session.session_id
    state = body.state.session or session_store.get(session_id)

    text, new_state = _dispatch(body, state, dikidi)
    session_store.put(session_id, new_state)
    return text, new_state


def _dispatch(body: AliceRequestBody, state: dict, dikidi: DikidiClient) -> tuple[str, dict]:
    if state.get("scenario") == "add_booking":
        return add_booking.handle(body, state, dikidi)

    text = body.request.command.strip().lower()

    if body.session.new and not text:
        return WELCOME_TEXT, {}

    if _is_add_booking_intent(text):
        return add_booking.start(body, dikidi)

    if _is_today_bookings_intent(text):
        return today_bookings.handle(body, dikidi)

    return WELCOME_TEXT, {}


def _is_add_booking_intent(text: str) -> bool:
    if "запиши" in text:
        return True
    if "добав" in text and "запис" in text:
        return True
    return any(phrase in text for phrase in ADD_BOOKING_KEYWORDS)


def _is_today_bookings_intent(text: str) -> bool:
    if "сколько" not in text:
        return False
    return any(word in text for word in TODAY_BOOKINGS_CONTEXT_WORDS)
