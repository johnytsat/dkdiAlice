"""Ручная прогонка диалога по шагам против локально запущенного вебхука.

Запуск:
    1) .venv\\Scripts\\uvicorn app.main:app --reload   (в отдельном терминале)
    2) .venv\\Scripts\\python scripts\\send_test_request.py
"""

import httpx

URL = "http://127.0.0.1:8000/alice/webhook"


def make_payload(command: str, state: dict, original: str | None = None, entities: list | None = None) -> dict:
    return {
        "meta": {"locale": "ru-RU", "timezone": "Europe/Moscow"},
        "request": {
            "command": command,
            "original_utterance": original if original is not None else command,
            "type": "SimpleUtterance",
            "nlu": {"entities": entities or []},
        },
        "session": {"new": state == {}, "message_id": 0, "session_id": "manual-test"},
        "state": {"session": state},
        "version": "1.0",
    }


def send(command: str, state: dict, original: str | None = None, entities: list | None = None) -> dict:
    payload = make_payload(command, state, original, entities)
    response = httpx.post(URL, json=payload, timeout=10)
    response.raise_for_status()
    data = response.json()
    print(f"> {command}")
    print(f"< {data['response']['text']}\n")
    return data["session_state"]


def main() -> None:
    state: dict = {}
    state = send("добавь запись", state)
    state = send("иван", state, original="Иван")
    state = send("89991234567", state)
    state = send("маникюр", state)
    state = send(
        "завтра",
        state,
        entities=[{"type": "YANDEX.DATETIME", "value": {"day": 1, "day_is_relative": True}}],
    )
    state = send(
        "в 15:00",
        state,
        entities=[
            {
                "type": "YANDEX.DATETIME",
                "value": {"hour": 15, "hour_is_relative": False, "minute": 0, "minute_is_relative": False},
            }
        ],
    )
    send("да", state)
    send("сколько записей на сегодня", {})


if __name__ == "__main__":
    main()
