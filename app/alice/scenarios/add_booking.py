"""FSM слот-филлинга для сценария "добавь запись".

Состояние хранится в session_state (который Алиса возвращает нам в следующем
запросе) в виде {"scenario": "add_booking", "step": ..., "data": {...}} —
никакой БД для диалога не требуется.
"""

from __future__ import annotations

from datetime import date, datetime
from datetime import time as time_cls
from typing import Any

from app.alice import nlu
from app.alice.models import AliceRequestBody
from app.dikidi.client import DikidiClient
from app.dikidi.models import Service

SLOT_ORDER = ["name", "phone", "service", "date", "time"]

QUESTIONS = {
    "name": "Как зовут клиента?",
    "phone": "Назовите номер телефона клиента.",
    "service": "На какую услугу записать?",
    "date": "На какую дату записать?",
    "time": "На какое время?",
}

YES_WORDS = ["да", "верно", "подтверждаю", "ага", "угу", "конечно"]
NO_WORDS = ["нет", "неверно", "не верно", "исправь", "измени"]
CANCEL_WORDS = {"отмена", "стоп", "отменить", "забудь"}

FIELD_WORDS = {
    "name": ["имя", "зовут"],
    "phone": ["телефон", "номер"],
    "service": ["услуг"],
    "date": ["дат"],
    "time": ["время", "час"],
}


def start(body: AliceRequestBody, dikidi: DikidiClient) -> tuple[str, dict]:
    data: dict[str, Any] = {}
    _extract_into(body, dikidi, data)
    return _ask_next_or_confirm(data)


def handle(body: AliceRequestBody, state: dict, dikidi: DikidiClient) -> tuple[str, dict]:
    text = body.request.command.strip().lower()
    data: dict[str, Any] = dict(state.get("data", {}))
    step = state.get("step")

    if text in CANCEL_WORDS:
        return "Хорошо, запись не создаю.", {}

    if step == "confirm":
        return _handle_confirm(text, data, dikidi)

    if step == "correct":
        return _handle_correct(text, data)

    focus_slot = step[len("ask_"):] if step and step.startswith("ask_") else None
    _extract_into(body, dikidi, data, focus_slot=focus_slot)
    return _ask_next_or_confirm(data)


def _extract_into(
    body: AliceRequestBody,
    dikidi: DikidiClient,
    data: dict[str, Any],
    focus_slot: str | None = None,
) -> None:
    text = body.request.command.strip().lower()
    original = body.request.original_utterance.strip()
    now = datetime.now()
    entities = body.request.nlu.entities

    if "phone" not in data:
        phone = nlu.extract_phone(text)
        if phone:
            data["phone"] = phone

    if "service_id" not in data:
        service = nlu.extract_service(text, dikidi.list_services())
        if service:
            data["service_id"] = service.id
            data["service_title"] = service.title

    if "date" not in data or "time" not in data:
        parsed_date, parsed_time = nlu.extract_datetime(entities, now)
        if parsed_date and "date" not in data:
            data["date"] = parsed_date.isoformat()
        if parsed_time and "time" not in data:
            data["time"] = parsed_time.strftime("%H:%M")

    if "name" not in data:
        name = nlu.extract_name_from_entities(entities) or nlu.extract_name(original)
        if name:
            data["name"] = name
        elif focus_slot == "name" and original:
            cleaned = nlu.clean_name_fallback(original)
            if cleaned:
                data["name"] = cleaned


def _missing_slot(data: dict[str, Any]) -> str | None:
    for slot in SLOT_ORDER:
        key = "service_id" if slot == "service" else slot
        if key not in data:
            return slot
    return None


def _ask_next_or_confirm(data: dict[str, Any]) -> tuple[str, dict]:
    missing = _missing_slot(data)
    if missing:
        state = {"scenario": "add_booking", "step": f"ask_{missing}", "data": data}
        return QUESTIONS[missing], state

    summary = (
        f"Записываю {data['name']}, телефон {data['phone']}, "
        f"на {data['service_title']}, {_format_date(data['date'])} в {data['time']}. Всё верно?"
    )
    state = {"scenario": "add_booking", "step": "confirm", "data": data}
    return summary, state


def _handle_confirm(text: str, data: dict[str, Any], dikidi: DikidiClient) -> tuple[str, dict]:
    if any(word in text for word in YES_WORDS):
        service = Service(id=data["service_id"], title=data["service_title"])
        client_id = dikidi.find_or_create_client(data["name"], data["phone"])
        booking_date = date.fromisoformat(data["date"])
        booking_time = time_cls.fromisoformat(data["time"])
        dikidi.create_booking(client_id, data["name"], data["phone"], service, booking_date, booking_time)
        text_response = (
            f"Записал {data['name']} на {data['service_title']} "
            f"{_format_date(data['date'])} в {data['time']}."
        )
        return text_response, {}

    if any(word in text for word in NO_WORDS):
        state = {"scenario": "add_booking", "step": "correct", "data": data}
        return "Что исправить: имя, телефон, услугу, дату или время?", state

    state = {"scenario": "add_booking", "step": "confirm", "data": data}
    return "Скажите да, если всё верно, или нет, если нужно что-то исправить.", state


def _handle_correct(text: str, data: dict[str, Any]) -> tuple[str, dict]:
    for slot, trigger_words in FIELD_WORDS.items():
        if any(word in text for word in trigger_words):
            key = "service_id" if slot == "service" else slot
            data.pop(key, None)
            if slot == "service":
                data.pop("service_title", None)
            state = {"scenario": "add_booking", "step": f"ask_{slot}", "data": data}
            return QUESTIONS[slot], state

    state = {"scenario": "add_booking", "step": "correct", "data": data}
    return "Не понял, что исправить. Скажите: имя, телефон, услугу, дату или время.", state


def _format_date(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d.%m.%Y")
