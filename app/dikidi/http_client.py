"""Реальная реализация DikidiClient через HTTP API Dikidi Business.

ВАЖНО: Dikidi не публикует открытую документацию API — конкретные URL, формат
запросов/ответов и способ авторизации выдаются вместе с партнёрским токеном
(Настройки -> Интеграция -> Доступ к API в личном кабинете Dikidi Business,
либо через персонального менеджера). Этот файл — заготовка с понятными местами
для правки (отмечены TODO), когда появятся токен, company_id и спецификация
эндпоинтов. До этого используйте DIKIDI_BACKEND=mock (см. app/config.py).
"""

from datetime import date, time

import httpx

from app.dikidi.client import DikidiClient
from app.dikidi.models import Booking, Service

BASE_URL = "https://api.dikidi.ru"  # TODO: заменить на реальный базовый URL из документации Dikidi


class HttpDikidiClient(DikidiClient):
    def __init__(self, token: str, company_id: str, default_staff_id: int = 0) -> None:
        if not token or not company_id:
            raise RuntimeError(
                "DIKIDI_TOKEN и DIKIDI_COMPANY_ID должны быть заданы для DIKIDI_BACKEND=http"
            )
        self.company_id = company_id
        self.default_staff_id = default_staff_id
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}"},  # TODO: уточнить схему авторизации
            timeout=10.0,
        )

    def list_services(self) -> list[Service]:
        # TODO: заменить путь/парсинг ответа на реальный эндпоинт списка услуг
        response = self._client.get(f"/company/{self.company_id}/services")
        response.raise_for_status()
        payload = response.json()
        return [
            Service(
                id=item["id"],
                title=item["title"],
                duration_minutes=item.get("duration", 60),
                price=item.get("price", 0.0),
            )
            for item in payload.get("data", [])
        ]

    def find_or_create_client(self, name: str, phone: str) -> int:
        # TODO: заменить на реальный эндпоинт поиска/создания клиента
        response = self._client.post(
            f"/company/{self.company_id}/clients",
            json={"name": name, "phone": phone},
        )
        response.raise_for_status()
        return response.json()["id"]

    def create_booking(
        self,
        client_id: int,
        client_name: str,
        client_phone: str,
        service: Service,
        booking_date: date,
        booking_time: time,
    ) -> int:
        # TODO: заменить на реальный эндпоинт создания записи
        response = self._client.post(
            f"/company/{self.company_id}/records",
            json={
                "client_id": client_id,
                "service_id": service.id,
                "staff_id": self.default_staff_id,
                "date": booking_date.isoformat(),
                "time": booking_time.strftime("%H:%M"),
            },
        )
        response.raise_for_status()
        return response.json()["id"]

    def get_bookings_for_date(self, booking_date: date) -> list[Booking]:
        # TODO: заменить на реальный эндпоинт списка записей за дату
        response = self._client.get(
            f"/company/{self.company_id}/records",
            params={"date": booking_date.isoformat()},
        )
        response.raise_for_status()
        payload = response.json()
        return [
            Booking(
                id=item["id"],
                client_name=item["client_name"],
                client_phone=item["client_phone"],
                service_title=item["service_title"],
                date=booking_date,
                time=time.fromisoformat(item["time"]),
            )
            for item in payload.get("data", [])
        ]
