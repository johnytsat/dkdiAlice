"""FSM слот-филлинга для сценария "добавь запись".

Состояние хранится в session_state (а для клиентов, которые его не возвращают —
в app.alice.session_store) в виде
{"scenario": "add_booking", "step": ..., "data": {...}}.

Услуг в записи может быть несколько: шаг ask_services принимает их по одной,
пока пользователь не скажет "всё"/"хватит"/"стоп".
"""

from __future__ import annotations

from datetime import date, datetime
from datetime import time as time_cls
from typing import Any

from app.alice import nlu
from app.alice.models import AliceRequestBody
from app.dikidi.client import DikidiClient
from app.dikidi.models import Service

SLOT_ORDER = ["name", "phone", "services", "date", "time"]

QUESTIONS = {
    "name": "Как зовут клиента?",
    "phone": "Назовите номер телефона клиента.",
    "services": "На какую услугу записать?",
    "date": "На какую дату записать?",
    "time": "На какое время?",
}

YES_WORDS = ["да", "верно", "подтверждаю", "ага", "угу", "конечно"]
NO_WORDS = ["нет", "неверно", "не верно", "исправь", "измени"]
CANCEL_WORDS = {"отмена", "отменить", "отмени", "забудь", "стоп"}

# Завершают перечисление услуг, но НЕ отменяют запись.
DONE_WORDS = {
    "всё", "все", "хватит", "достаточно", "готово", "стоп",
    "это всё", "это все", "больше ничего", "больше не надо", "нет",
}

CATALOG_HINT_LIMIT = 8

FIELD_WORDS = {
    "name": ["имя", "зовут"],
    "phone": ["телефон", "номер"],
    "services": ["услуг", "процедур"],
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

    if step == "ask_services":
        return _handle_services_step(text, data, dikidi)

    if text in CANCEL_WORDS:
        return "Хорошо, запись не создаю.", {}

    if step == "confirm":
        return _handle_confirm(text, data, dikidi)

    if step == "correct":
        return _handle_correct(text, data)

    focus_slot = step[len("ask_"):] if step and step.startswith("ask_") else None
    _extract_into(body, dikidi, data, focus_slot=focus_slot)
    return _ask_next_or_confirm(data)


def _handle_services_step(
    text: str, data: dict[str, Any], dikidi: DikidiClient
) -> tuple[str, dict]:
    services: list[dict] = list(data.get("services", []))

    if text in DONE_WORDS:
        if services:
            data["services_confirmed"] = True
            return _ask_next_or_confirm(data)
        if text in CANCEL_WORDS:
            return "Хорошо, запись не создаю.", {}
        return _services_state("Нужна хотя бы одна услуга. На какую услугу записать?", data)

    if text in CANCEL_WORDS:
        return "Хорошо, запись не создаю.", {}

    catalog = dikidi.list_services()
    match = nlu.extract_service(text, catalog)

    if match is None:
        return _services_state(
            f"Не нашёл такую услугу. {_catalog_hint(catalog)} "
            "Назовите услугу ещё раз или скажите «всё», чтобы продолжить.",
            data,
        )

    if any(item["id"] == match.id for item in services):
        return _services_state(
            f"{match.title.capitalize()} уже в списке. "
            "Назовите ещё услугу или скажите «всё», если это все.",
            data,
        )

    services.append({"id": match.id, "title": match.title})
    data["services"] = services
    return _services_state(
        f"Добавил {match.title}. Назовите ещё услугу или скажите «всё», если это все.",
        data,
    )


def _services_state(text: str, data: dict[str, Any]) -> tuple[str, dict]:
    return text, {"scenario": "add_booking", "step": "ask_services", "data": data}


def _catalog_hint(catalog: list[Service]) -> str:
    titles = [service.title for service in catalog[:CATALOG_HINT_LIMIT]]
    hint = f"Доступны: {', '.join(titles)}"
    if len(catalog) > CATALOG_HINT_LIMIT:
        hint += " и другие"
    return hint + "."


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

    if not data.get("services"):
        service = nlu.extract_service(text, dikidi.list_services())
        if service:
            data["services"] = [{"id": service.id, "title": service.title}]

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
        if slot == "services":
            if not data.get("services_confirmed"):
                return slot
        elif slot not in data:
            return slot
    return None


def _ask_next_or_confirm(data: dict[str, Any]) -> tuple[str, dict]:
    missing = _missing_slot(data)
    if missing == "services":
        services = data.get("services", [])
        if services:
            return _services_state(
                f"Пока записал: {_format_services(services)}. "
                "Назовите ещё услугу или скажите «всё», если это все.",
                data,
            )
        return _services_state(QUESTIONS["services"], data)

    if missing:
        state = {"scenario": "add_booking", "step": f"ask_{missing}", "data": data}
        return QUESTIONS[missing], state

    summary = (
        f"Записываю {data['name']}, телефон {data['phone']}, "
        f"на {_format_services(data['services'])}, "
        f"{_format_date(data['date'])} в {data['time']}. Всё верно?"
    )
    state = {"scenario": "add_booking", "step": "confirm", "data": data}
    return summary, state


def _handle_confirm(text: str, data: dict[str, Any], dikidi: DikidiClient) -> tuple[str, dict]:
    if any(word in text for word in YES_WORDS):
        services = [Service(id=item["id"], title=item["title"]) for item in data["services"]]
        client_id = dikidi.find_or_create_client(data["name"], data["phone"])
        booking_date = date.fromisoformat(data["date"])
        booking_time = time_cls.fromisoformat(data["time"])
        dikidi.create_booking(
            client_id, data["name"], data["phone"], services, booking_date, booking_time
        )
        text_response = (
            f"Записал {data['name']} на {_format_services(data['services'])} "
            f"{_format_date(data['date'])} в {data['time']}."
        )
        return text_response, {}

    if any(word in text for word in NO_WORDS):
        state = {"scenario": "add_booking", "step": "correct", "data": data}
        return "Что исправить: имя, телефон, услуги, дату или время?", state

    state = {"scenario": "add_booking", "step": "confirm", "data": data}
    return "Скажите да, если всё верно, или нет, если нужно что-то исправить.", state


def _handle_correct(text: str, data: dict[str, Any]) -> tuple[str, dict]:
    for slot, trigger_words in FIELD_WORDS.items():
        if any(word in text for word in trigger_words):
            if slot == "services":
                data.pop("services", None)
                data.pop("services_confirmed", None)
                return _services_state(QUESTIONS["services"], data)
            data.pop(slot, None)
            state = {"scenario": "add_booking", "step": f"ask_{slot}", "data": data}
            return QUESTIONS[slot], state

    state = {"scenario": "add_booking", "step": "correct", "data": data}
    return "Не понял, что исправить. Скажите: имя, телефон, услуги, дату или время.", state


def _format_services(services: list[dict]) -> str:
    return ", ".join(item["title"] for item in services)


def _format_date(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d.%m.%Y")
