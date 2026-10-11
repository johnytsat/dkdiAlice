"""Выдаёт клиента Dikidi по текущим учётным данным.

Клиента нельзя создать один раз на старте: в режиме sdk данные могут появиться
позже — после привязки на странице /setup. Провайдер кеширует клиента и
пересобирает его, когда учётные данные меняются.

get() возвращает None, если навык ещё не настроен — тогда диалог предлагает
привязку вместо того, чтобы падать.
"""

from __future__ import annotations

import logging
import threading

from app.credentials import store
from app.dikidi.client import DikidiClient

logger = logging.getLogger(__name__)


class DikidiProvider:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: DikidiClient | None = None
        store.on_change(self.invalidate)

    def invalidate(self) -> None:
        with self._lock:
            self._client = None
        logger.info("Учётные данные Dikidi изменились, клиент будет пересобран")

    def is_configured(self) -> bool:
        from app.config import settings

        backend = settings.dikidi_backend
        if backend == "mock":
            return True
        if backend == "http":
            return bool(settings.dikidi_token and store.get().company_id)
        return store.get().is_complete

    def get(self) -> DikidiClient | None:
        if not self.is_configured():
            return None

        with self._lock:
            if self._client is None:
                self._client = self._build()
            return self._client

    def _build(self) -> DikidiClient:
        from app.config import settings

        backend = settings.dikidi_backend
        credentials = store.get()

        if backend == "sdk":
            from app.dikidi.sdk_client import SdkDikidiClient

            logger.info("Создаю клиента Dikidi (sdk): %s", credentials.masked())
            return SdkDikidiClient(
                phone=credentials.phone,
                password=credentials.password,
                company_id=credentials.company_id,
                default_staff_id=credentials.default_staff_id,
            )

        if backend == "http":
            from app.dikidi.http_client import HttpDikidiClient

            return HttpDikidiClient(
                token=settings.dikidi_token,
                company_id=credentials.company_id,
                default_staff_id=credentials.default_staff_id,
            )

        from app.dikidi.mock_client import MockDikidiClient

        return MockDikidiClient()


provider = DikidiProvider()
