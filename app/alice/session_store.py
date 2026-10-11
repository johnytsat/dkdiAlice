"""Серверное хранилище состояния диалога.

Некоторые клиенты Алисы (например, поиск Яндекса на Android) не возвращают
обратно session_state, который мы отправили в ответе — поле state в запросе
просто отсутствует. Поэтому состояние дублируется здесь, с привязкой к
session_id, и используется, когда клиент его не прислал.
"""

from __future__ import annotations

import time
from typing import Any

SESSION_TTL_SECONDS = 600
MAX_SESSIONS = 10_000

_store: dict[str, tuple[float, dict[str, Any]]] = {}


def get(session_id: str) -> dict[str, Any]:
    entry = _store.get(session_id)
    if entry is None:
        return {}
    saved_at, state = entry
    if time.monotonic() - saved_at > SESSION_TTL_SECONDS:
        del _store[session_id]
        return {}
    return state


def put(session_id: str, state: dict[str, Any]) -> None:
    if not state:
        _store.pop(session_id, None)
        return
    _prune()
    _store[session_id] = (time.monotonic(), state)


def _prune() -> None:
    now = time.monotonic()
    expired = [key for key, (saved_at, _) in _store.items() if now - saved_at > SESSION_TTL_SECONDS]
    for key in expired:
        del _store[key]

    if len(_store) >= MAX_SESSIONS:
        oldest = sorted(_store.items(), key=lambda item: item[1][0])[: len(_store) // 2]
        for key, _ in oldest:
            del _store[key]
