from dataclasses import dataclass
from datetime import date, time


@dataclass
class Service:
    id: int
    title: str
    duration_minutes: int = 60
    price: float = 0.0


@dataclass
class Client:
    id: int
    name: str
    phone: str


@dataclass
class Booking:
    id: int
    client_name: str
    client_phone: str
    service_title: str
    date: date
    time: time
