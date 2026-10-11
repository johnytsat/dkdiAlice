from dataclasses import dataclass
from datetime import date, time

# Mock-бекенд нумерует сущности целыми, Dikidi отдаёт числовые строки —
# поэтому id нигде не участвует в арифметике, только в сравнении и передаче.
EntityId = int | str


@dataclass
class Service:
    id: EntityId
    title: str
    duration_minutes: int = 60
    price: float = 0.0


@dataclass
class Client:
    id: EntityId
    name: str
    phone: str


@dataclass
class Booking:
    id: EntityId
    client_name: str
    client_phone: str
    service_titles: list[str]
    date: date
    time: time
