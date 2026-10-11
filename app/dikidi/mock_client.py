"""In-memory реализация DikidiClient для разработки и тестов, без сети."""

import itertools
from datetime import date, time

from app.dikidi.client import DikidiClient
from app.dikidi.models import Booking, Client, Service

_DEFAULT_SERVICES = [
    Service(id=1, title="маникюр", duration_minutes=60, price=1500),
    Service(id=2, title="педикюр", duration_minutes=90, price=2000),
    Service(id=3, title="стрижка", duration_minutes=45, price=1200),
    Service(id=4, title="окрашивание", duration_minutes=120, price=4500),
    Service(id=5, title="массаж", duration_minutes=60, price=2500),
]


class MockDikidiClient(DikidiClient):
    def __init__(self) -> None:
        self._services = list(_DEFAULT_SERVICES)
        self._clients: dict[int, Client] = {}
        self._bookings: dict[int, Booking] = {}
        self._client_ids = itertools.count(1)
        self._booking_ids = itertools.count(1)

    def list_services(self) -> list[Service]:
        return list(self._services)

    def find_or_create_client(self, name: str, phone: str) -> int:
        for client in self._clients.values():
            if client.phone == phone:
                return client.id
        client_id = next(self._client_ids)
        self._clients[client_id] = Client(id=client_id, name=name, phone=phone)
        return client_id

    def create_booking(
        self,
        client_id: int,
        client_name: str,
        client_phone: str,
        service: Service,
        booking_date: date,
        booking_time: time,
    ) -> int:
        booking_id = next(self._booking_ids)
        self._bookings[booking_id] = Booking(
            id=booking_id,
            client_name=client_name,
            client_phone=client_phone,
            service_title=service.title,
            date=booking_date,
            time=booking_time,
        )
        return booking_id

    def get_bookings_for_date(self, booking_date: date) -> list[Booking]:
        bookings = [b for b in self._bookings.values() if b.date == booking_date]
        return sorted(bookings, key=lambda b: b.time)
