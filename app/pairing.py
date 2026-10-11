"""Одноразовые коды привязки: связывают страницу /setup с тем, кто позвал навык.

Страница настройки доступна всем, кто знает адрес, поэтому код обязателен —
иначе посторонний мог бы подменить аккаунт Dikidi, к которому обращается навык.
Код выдаётся только по запросу из диалога, живёт 10 минут, срабатывает один раз,
а перебор ограничен и числом попыток на код, и общей блокировкой.
"""

from __future__ import annotations

import secrets
import threading
import time

CODE_TTL_SECONDS = 600
MAX_ATTEMPTS_PER_CODE = 5
MAX_FAILED_TOTAL = 20
LOCKOUT_SECONDS = 900
CODE_DIGITS = 6


class PairingError(RuntimeError):
    """Код не подошёл: не найден, истёк, исчерпан или включена блокировка."""


class _Code:
    __slots__ = ("user_id", "expires_at", "attempts")

    def __init__(self, user_id: str, expires_at: float) -> None:
        self.user_id = user_id
        self.expires_at = expires_at
        self.attempts = 0


class PairingCodes:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._codes: dict[str, _Code] = {}
        self._failed_total = 0
        self._locked_until = 0.0

    def issue(self, user_id: str) -> str:
        now = time.monotonic()
        with self._lock:
            self._drop_expired(now)
            # Один активный код на пользователя, чтобы старые не копились.
            for code, entry in list(self._codes.items()):
                if entry.user_id == user_id:
                    del self._codes[code]

            code = "".join(str(secrets.randbelow(10)) for _ in range(CODE_DIGITS))
            while code in self._codes:
                code = "".join(str(secrets.randbelow(10)) for _ in range(CODE_DIGITS))
            self._codes[code] = _Code(user_id, now + CODE_TTL_SECONDS)
            return code

    def verify(self, code: str) -> str:
        """Возвращает user_id, которому выдавался код, и гасит код."""
        code = code.strip()
        now = time.monotonic()
        with self._lock:
            if now < self._locked_until:
                raise PairingError("Слишком много неудачных попыток. Попробуйте позже.")

            self._drop_expired(now)
            entry = self._codes.get(code.strip())
            if entry is None:
                self._register_failure(now)
                raise PairingError("Код неверный или истёк. Запросите новый у Алисы.")

            entry.attempts += 1
            if entry.attempts > MAX_ATTEMPTS_PER_CODE:
                del self._codes[code]
                self._register_failure(now)
                raise PairingError("Код исчерпан. Запросите новый у Алисы.")

            del self._codes[code]
            self._failed_total = 0
            return entry.user_id

    def _drop_expired(self, now: float) -> None:
        for code, entry in list(self._codes.items()):
            if entry.expires_at <= now:
                del self._codes[code]

    def _register_failure(self, now: float) -> None:
        self._failed_total += 1
        if self._failed_total >= MAX_FAILED_TOTAL:
            self._locked_until = now + LOCKOUT_SECONDS
            self._failed_total = 0

    def reset(self) -> None:
        """Только для тестов."""
        with self._lock:
            self._codes.clear()
            self._failed_total = 0
            self._locked_until = 0.0


codes = PairingCodes()
