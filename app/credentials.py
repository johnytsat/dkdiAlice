"""Учётные данные Dikidi, которые можно задать во время работы навыка.

Источники, в порядке приоритета:
  1. то, что ввели на странице /setup (живёт в памяти процесса);
  2. переменные окружения (см. .env.example) — используются как начальное
     значение при старте.

Память процесса намеренно: пароль не ложится на диск. Обратная сторона —
после перезапуска (а на бесплатном Render он происходит при каждом
просыпании) привязку нужно повторить, если данные не прописаны в окружении.
Страница /setup после сохранения показывает готовый блок для окружения.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace, field


@dataclass(frozen=True)
class DikidiCredentials:
    phone: str = ""
    password: str = field(default="", repr=False)
    company_id: str = ""
    default_staff_id: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.phone and self.password and self.company_id)

    def masked(self) -> dict[str, str]:
        """Безопасное представление для логов и страницы — без пароля."""
        return {
            "phone": _mask_phone(self.phone),
            "company_id": self.company_id,
            "default_staff_id": self.default_staff_id or "(первый из каталога)",
            "password": "**** задан" if self.password else "(не задан)",
        }


def _mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return phone
    return f"{phone[:2]}***{phone[-4:]}"


class CredentialStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._credentials: DikidiCredentials | None = None
        self._listeners: list = []

    def on_change(self, callback) -> None:
        """Подписка: нужна, чтобы пересобрать клиента Dikidi после привязки."""
        self._listeners.append(callback)

    def get(self) -> DikidiCredentials:
        with self._lock:
            if self._credentials is None:
                self._credentials = _from_settings()
            return self._credentials

    def set(self, credentials: DikidiCredentials) -> None:
        with self._lock:
            self._credentials = credentials
        for callback in self._listeners:
            callback()

    def update_staff_id(self, staff_id: str) -> None:
        self.set(replace(self.get(), default_staff_id=staff_id))

    def clear(self) -> None:
        """Только для тестов: сбросить к значениям из окружения."""
        with self._lock:
            self._credentials = None
        for callback in self._listeners:
            callback()


def _from_settings() -> DikidiCredentials:
    from app.config import settings

    return DikidiCredentials(
        phone=settings.dikidi_phone,
        password=settings.dikidi_password,
        company_id=settings.dikidi_company_id,
        default_staff_id=settings.dikidi_default_staff_id,
    )


store = CredentialStore()
