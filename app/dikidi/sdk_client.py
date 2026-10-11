"""Реализация DikidiClient через неофициальный пакет dikidi-api-client.

Пакет логинится в Dikidi Business по телефону и паролю (как браузер) и ходит
по веб-шлюзам CRM — это обход того, что публичного API у Dikidi нет. Отсюда
следствия, о которых стоит помнить:

* Версия пакета жёстко закреплена в requirements.txt. Код версии 0.1.3 был
  проверен: учётные данные уходят только на домены dikidi.ru/dikidi.net.
  Обновлять только после повторной проверки.
* Dikidi может в любой момент поменять вёрстку/шлюзы — тогда вызовы отвалятся.
  Поэтому ошибки SDK наверх не пробрасываются как пятисотка: сценарии получают
  исключение DikidiUnavailable и отвечают пользователю по-человечески.
* Пароль даёт полный доступ к аккаунту; держите его только в переменных
  окружения (см. .env.example), никогда в коде или git.

Авторизация ленивая: login происходит при первом реальном обращении, а не на
старте приложения — иначе холодный старт на Render падал бы без доступа к сети.
"""

from __future__ import annotations

import logging
import hashlib
import re
import tempfile
import threading
import time as time_module
from datetime import date, time
from pathlib import Path

from app.dikidi.client import DikidiClient, DikidiUnavailable, BookingUncertain
from app.dikidi.models import Booking, Service

logger = logging.getLogger(__name__)

SERVICES_TTL_SECONDS = 600
# Клиент не найден в базе — Dikidi создаст его сам из имени и телефона записи.
NEW_CLIENT_ID = 0


class SdkDikidiClient(DikidiClient):
    def __init__(
        self,
        phone: str,
        password: str,
        company_id: str,
        default_staff_id: int | str = 0,
        session_file: str | Path | None = None,
    ) -> None:
        if not phone or not password or not company_id:
            raise RuntimeError(
                "Для DIKIDI_BACKEND=sdk нужны DIKIDI_PHONE, DIKIDI_PASSWORD и DIKIDI_COMPANY_ID"
            )
        self._phone = phone
        self._password = password
        self._company_id = str(company_id)
        self._configured_staff_id = str(default_staff_id) if default_staff_id else ""
        # На Render файловая система эфемерная, поэтому кука живёт в tempdir и
        # после холодного старта SDK просто логинится заново.
        self._session_file = Path(session_file) if session_file else (
            Path(tempfile.gettempdir()) / ("dikidi_" + hashlib.sha256(
                f"{phone}:{company_id}:{password}".encode()
            ).hexdigest() + "_cookies.json")
        )

        self._lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._api = None
        self._services_cache: list[Service] = []
        self._services_cached_at = 0.0
        self._master_id: str | None = None

    # --- инфраструктура -------------------------------------------------

    def _get_api(self):
        with self._lock:
            if self._api is None:
                try:
                    from dikidi import DikidiAPI
                except ImportError as exc:  # pragma: no cover - зависит от окружения
                    raise DikidiUnavailable(
                        "Пакет dikidi-api-client не установлен"
                    ) from exc
                self._api = DikidiAPI(
                    phone=self._phone,
                    password=self._password,
                    company_id=self._company_id,
                    session_file=self._session_file,
                )
            return self._api

    def _call(self, description: str, func, *args, **kwargs):
        """Единая точка вызова SDK: логирует и приводит любые сбои к DikidiUnavailable."""
        try:
            with self._request_lock:
                return func(*args, **kwargs)
        except DikidiUnavailable:
            raise
        except Exception as exc:
            logger.warning("Dikidi SDK: %s не удалось (%s)", description, type(exc).__name__)
            raise DikidiUnavailable(f"Dikidi недоступна: {description}") from exc

    # --- DikidiClient ---------------------------------------------------

    def list_services(self) -> list[Service]:
        fresh = time_module.monotonic() - self._services_cached_at < SERVICES_TTL_SECONDS
        if self._services_cache and fresh:
            return list(self._services_cache)

        api = self._get_api()
        raw = self._call("получение списка услуг", api.catalog.get_services)
        services = [
            Service(
                id=item.id,
                title=item.name.strip().lower(),
                duration_minutes=item.duration or 60,
                price=item.cost or 0.0,
            )
            for item in raw
            if getattr(item, "name", "").strip()
        ]
        if services:
            self._services_cache = services
            self._services_cached_at = time_module.monotonic()
        return list(services)

    def find_or_create_client(self, name: str, phone: str) -> int | str:
        api = self._get_api()
        digits = _phone_digits(phone)
        found = self._call("поиск клиента", api.clients.search, digits or phone, 20)
        for candidate in found or []:
            if _phone_digits(getattr(candidate, "phone", "")) == digits:
                return candidate.id
        # Отдельно создавать клиента не нужно: Dikidi сама завёдет его при
        # сохранении записи, если передать client_id=0 вместе с именем и телефоном.
        return NEW_CLIENT_ID

    def create_booking(self, *args, **kwargs) -> int | str:
        try:
            return self._create_booking(*args, **kwargs)
        except Exception as exc:
            raise BookingUncertain("Проверьте результат в журнале Dikidi") from exc

    def _create_booking(
        self,
        client_id: int | str,
        client_name: str,
        client_phone: str,
        services: list[Service],
        booking_date: date,
        booking_time: time,
    ) -> int | str:
        from dikidi import BookingRequest

        api = self._get_api()
        request = BookingRequest(
            master_id=self._resolve_master_id(),
            service_ids=[service.id for service in services],
            time_str=f"{booking_date.isoformat()} {booking_time.strftime('%H:%M:%S')}",
            client_name=client_name,
            client_phone=client_phone,
            client_id=client_id or None,
        )
        # book() теряет record_id, возвращая только ответ save_appointment.
        reservation = self._call(
            "резервирование времени", api.appointments.reserve_time,
            master_id=request.master_id, service_ids=request.service_ids,
            time_str=request.time_str,
        )
        if not reservation.record_id:
            raise DikidiUnavailable("Dikidi не вернула номер записи")
        self._call(
            "сохранение записи", api.appointments.save_appointment,
            record_id=reservation.record_id, unique_key=reservation.unique_key,
            client_name=request.client_name, client_phone=request.client_phone,
            client_id=request.client_id,
        )
        # HTTP 200 и даже пустой JSON ещё не означают сохранённый визит.
        records = self._call("проверка сохранения", api.appointments.get_records,
                             booking_date.isoformat(), booking_date.isoformat())
        if not any(str(r.id) == str(reservation.record_id)
                   and not r.is_block
                   and _phone_digits(r.client_phone) == _phone_digits(client_phone)
                   for r in records):
            raise DikidiUnavailable("Сохранение записи не подтверждено журналом")
        return reservation.record_id

    def get_bookings_for_date(self, booking_date: date) -> list[Booking]:
        api = self._get_api()
        iso = booking_date.isoformat()
        records = self._call("получение записей", api.appointments.get_records, iso, iso)

        bookings = []
        for record in records or []:
            # is_block — служебное время (дежурства, санобработка), не клиент.
            if getattr(record, "is_block", False):
                continue
            parsed_time = _parse_time(getattr(record, "time_start", ""))
            if parsed_time is None:
                continue
            bookings.append(
                Booking(
                    id=record.id,
                    client_name=(record.client_name or "Без имени").strip(),
                    client_phone=record.client_phone or "",
                    service_titles=list(record.services or []),
                    date=booking_date,
                    time=parsed_time,
                )
            )
        return sorted(bookings, key=lambda item: item.time)

    # --- вспомогательное ------------------------------------------------

    def _resolve_master_id(self) -> str:
        if self._configured_staff_id:
            return self._configured_staff_id
        if self._master_id:
            return self._master_id

        api = self._get_api()
        masters = self._call("получение списка мастеров", api.catalog.get_masters)
        if not masters:
            raise DikidiUnavailable("В аккаунте Dikidi не найдено ни одного мастера")
        self._master_id = str(masters[0].id)
        logger.info("Dikidi SDK: мастер по умолчанию не задан, использую %s", self._master_id)
        return self._master_id


def _phone_digits(phone: str) -> str:
    """Последние 10 цифр — чтобы +7/8/без кода сравнивались между собой."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _parse_time(raw: str) -> time | None:
    parts = (raw or "").strip().split(":")
    if len(parts) < 2:
        return None
    try:
        return time(hour=int(parts[0]), minute=int(parts[1]))
    except ValueError:
        return None
