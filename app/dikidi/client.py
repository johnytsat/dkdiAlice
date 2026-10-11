from abc import ABC, abstractmethod
from datetime import date, time

from app.dikidi.models import Booking, Service


class DikidiUnavailable(RuntimeError):
    """Dikidi недоступна или сменила шлюзы — навык должен сказать это вслух."""


class BookingUncertain(DikidiUnavailable):
    """После попытки записи нельзя безопасно повторять операцию автоматически."""


class DikidiClient(ABC):
    """Интерфейс к Dikidi. Конкретная реализация подключается через app.config.settings.dikidi_backend."""

    @abstractmethod
    def list_services(self) -> list[Service]:
        """Список услуг компании — используется для сопоставления произнесённой услуги."""

    @abstractmethod
    def find_or_create_client(self, name: str, phone: str) -> int | str:
        """Возвращает id клиента Dikidi, создавая его при отсутствии."""

    @abstractmethod
    def create_booking(
        self,
        client_id: int | str,
        client_name: str,
        client_phone: str,
        services: list[Service],
        booking_date: date,
        booking_time: time,
    ) -> int | str:
        """Создаёт запись в Dikidi на одну или несколько услуг, возвращает id записи."""

    @abstractmethod
    def get_bookings_for_date(self, booking_date: date) -> list[Booking]:
        """Все записи на указанную дату."""


def get_dikidi_client() -> DikidiClient:
    from app.config import settings

    if settings.dikidi_backend == "sdk":
        from app.dikidi.sdk_client import SdkDikidiClient

        return SdkDikidiClient(
            phone=settings.dikidi_phone,
            password=settings.dikidi_password,
            company_id=settings.dikidi_company_id,
            default_staff_id=settings.dikidi_default_staff_id,
        )

    if settings.dikidi_backend == "http":
        from app.dikidi.http_client import HttpDikidiClient

        return HttpDikidiClient(
            token=settings.dikidi_token,
            company_id=settings.dikidi_company_id,
            default_staff_id=settings.dikidi_default_staff_id,
        )

    from app.dikidi.mock_client import MockDikidiClient

    return MockDikidiClient()
