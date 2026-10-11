from __future__ import annotations

from datetime import datetime

from app.alice import nlu
from app.alice.models import AliceRequestBody
from app.dikidi.client import DikidiClient


def handle(body: AliceRequestBody, dikidi: DikidiClient) -> tuple[str, dict]:
    now = datetime.now()
    entities = body.request.nlu.entities
    target_date, _ = nlu.extract_datetime(entities, now)
    if target_date is None:
        target_date = now.date()

    bookings = dikidi.get_bookings_for_date(target_date)

    day_word = "Сегодня" if target_date == now.date() else f"На {target_date.strftime('%d.%m.%Y')}"

    if not bookings:
        return f"{day_word} записей нет.", {}

    times = ", ".join(f"в {b.time.strftime('%H:%M')} — {b.client_name}" for b in bookings)
    text = f"{day_word} {len(bookings)} {_pluralize_records(len(bookings))}: {times}."
    return text, {}


def _pluralize_records(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "запись"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "записи"
    return "записей"
