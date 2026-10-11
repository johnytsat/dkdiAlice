from abc import ABC, abstractmethod
from datetime import date, time

from app.dikidi.models import Booking, Service


class DikidiClient(ABC):
    """Интерфейс к Dikidi. Конкретная реализация подключается через app.config.settings.dikidi_backend."""

    @abstractmethod
    def list_services(self) -> list[Service]:
        """Список услуг компании — используется для сопоставления произнесённой услуги."""

    @abstractmethod
    def find_or_create_client(self, name: str, phone: str) -> int:
        """Возвращает id клиента Dikidi, создавая его при отсутствии."""

    @abstractmethod
    def create_booking(
        self,
        client_id: int,
        client_name: str,
        client_phone: str,
        service: Service,
        booking_date: date,
        booking_time: time,
    ) -> int:
        """Создаёт запись в Dikidi, возвращает id записи."""

    @abstractmethod
    def get_bookings_for_date(self, booking_date: date) -> list[Booking]:
        """Все записи на указанную дату."""


def get_dikidi_client() -> DikidiClient:
    from app.config import settings

    if settings.dikidi_backend == "http":
        from app.dikidi.http_client import HttpDikidiClient

        return HttpDikidiClient(
            token=settings.dikidi_token,
            company_id=settings.dikidi_company_id,
            default_staff_id=settings.dikidi_default_staff_id,
        )

    from app.dikidi.mock_client import MockDikidiClient

    return MockDikidiClient()
