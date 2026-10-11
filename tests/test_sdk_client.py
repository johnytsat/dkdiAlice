"""Тесты SdkDikidiClient на поддельном SDK — без сети и реальных учётных данных.

Проверяем именно маппинг между Dikidi и нашими моделями: там, где форматы
выяснены по исходникам пакета (time_str как "YYYY-MM-DD HH:MM:SS", отбрасывание
служебных блокировок, сравнение телефонов), ошибка была бы не видна до продакшена.
"""

from dataclasses import dataclass, field
from datetime import date, time
from types import SimpleNamespace

import pytest

from app.dikidi.client import DikidiUnavailable
from app.dikidi.models import Service
from app.dikidi.sdk_client import NEW_CLIENT_ID, SdkDikidiClient


@dataclass
class FakeSdkService:
    id: str
    name: str
    cost: float = 0.0
    duration: int = 0


@dataclass
class FakeSdkMaster:
    id: str
    name: str


@dataclass
class FakeSdkClient:
    id: str
    name: str
    phone: str


@dataclass
class FakeSdkRecord:
    id: str
    time_start: str
    client_name: str | None = None
    client_phone: str | None = None
    services: list[str] = field(default_factory=list)
    is_block: bool = False


class FakeCatalog:
    def __init__(self, services, masters):
        self._services = services
        self._masters = masters
        self.services_calls = 0

    def get_services(self):
        self.services_calls += 1
        return self._services

    def get_masters(self):
        return self._masters


class FakeAppointments:
    def __init__(self, records=None):
        self._records = records or []
        self.booked = []
        self.records_args = None

    def get_records(self, date_from, date_to):
        self.records_args = (date_from, date_to)
        return self._records

    def reserve_time(self, **kwargs):
        self.booked.append(SimpleNamespace(**kwargs))
        return SimpleNamespace(record_id="999", unique_key="key")

    def save_appointment(self, **kwargs):
        self.booked[-1].__dict__.update(kwargs)
        self._records.append(FakeSdkRecord("999", "15:00", kwargs["client_name"], kwargs["client_phone"]))
        return {"success": True}


class FakeClients:
    def __init__(self, found=None):
        self._found = found or []
        self.query = None

    def search(self, query, limit=20):
        self.query = query
        return self._found


class FakeApi:
    def __init__(self, services=None, masters=None, records=None, found_clients=None):
        self.catalog = FakeCatalog(
            services if services is not None else [FakeSdkService("11", "Маникюр", 1500, 60)],
            masters if masters is not None else [FakeSdkMaster("777", "Мастер")],
        )
        self.appointments = FakeAppointments(records)
        self.clients = FakeClients(found_clients)


def make_client(api, **kwargs):
    client = SdkDikidiClient(
        phone="+70000000000",
        password="secret",
        company_id="1400000",
        **kwargs,
    )
    client._api = api
    return client


def test_requires_credentials():
    with pytest.raises(RuntimeError):
        SdkDikidiClient(phone="", password="", company_id="")


def test_list_services_maps_and_lowercases_titles():
    api = FakeApi(services=[FakeSdkService("11", "  Руки Полностью  ", 900, 30)])
    services = make_client(api).list_services()

    assert len(services) == 1
    assert services[0].id == "11"
    assert services[0].title == "руки полностью"
    assert services[0].duration_minutes == 30
    assert services[0].price == 900


def test_list_services_skips_nameless_and_defaults_duration():
    api = FakeApi(services=[FakeSdkService("1", "Стрижка", 0, 0), FakeSdkService("2", "   ")])
    services = make_client(api).list_services()

    assert [s.title for s in services] == ["стрижка"]
    assert services[0].duration_minutes == 60


def test_list_services_is_cached():
    api = FakeApi()
    client = make_client(api)
    client.list_services()
    client.list_services()
    assert api.catalog.services_calls == 1


def test_create_booking_builds_full_datetime_and_service_ids():
    api = FakeApi()
    client = make_client(api, default_staff_id="42")

    client.create_booking(
        client_id="5",
        client_name="Анна",
        client_phone="+79035523232",
        services=[Service(id="11", title="живот"), Service(id="12", title="спина")],
        booking_date=date(2026, 10, 12),
        booking_time=time(15, 0),
    )

    request = api.appointments.booked[0]
    assert request.time_str == "2026-10-12 15:00:00"
    assert request.service_ids == ["11", "12"]
    assert request.master_id == "42"
    assert request.client_id == "5"


def test_create_booking_sends_none_client_id_for_new_client():
    api = FakeApi()
    client = make_client(api, default_staff_id="42")

    client.create_booking(
        client_id=NEW_CLIENT_ID,
        client_name="Новый",
        client_phone="+79035523232",
        services=[Service(id="11", title="живот")],
        booking_date=date(2026, 10, 12),
        booking_time=time(9, 30),
    )

    assert api.appointments.booked[0].client_id is None


def test_master_id_falls_back_to_first_from_catalog():
    api = FakeApi(masters=[FakeSdkMaster("555", "Первый")])
    client = make_client(api)

    client.create_booking(
        client_id=0,
        client_name="Анна",
        client_phone="+79035523232",
        services=[Service(id="11", title="живот")],
        booking_date=date(2026, 10, 12),
        booking_time=time(15, 0),
    )

    assert api.appointments.booked[0].master_id == "555"


def test_missing_masters_raises_unavailable():
    client = make_client(FakeApi(masters=[]))
    with pytest.raises(DikidiUnavailable):
        client.create_booking(
            client_id=0,
            client_name="Анна",
            client_phone="+79035523232",
            services=[Service(id="11", title="живот")],
            booking_date=date(2026, 10, 12),
            booking_time=time(15, 0),
        )


def test_get_bookings_filters_blocks_and_sorts():
    api = FakeApi(
        records=[
            FakeSdkRecord("2", "16:00:00", "Пётр", "+79000000002", ["стрижка"]),
            FakeSdkRecord("3", "12:00:00", "[Служебное время]", None, [], is_block=True),
            FakeSdkRecord("1", "09:30:00", "Анна", "+79000000001", ["живот", "спина"]),
        ]
    )
    bookings = make_client(api).get_bookings_for_date(date(2026, 10, 12))

    assert [b.time.strftime("%H:%M") for b in bookings] == ["09:30", "16:00"]
    assert bookings[0].service_titles == ["живот", "спина"]
    assert api.appointments.records_args == ("2026-10-12", "2026-10-12")


def test_get_bookings_tolerates_short_time_and_missing_name():
    api = FakeApi(
        records=[
            FakeSdkRecord("1", "10:15", None, None, []),
            FakeSdkRecord("2", "", "Бракованная", None, []),
        ]
    )
    bookings = make_client(api).get_bookings_for_date(date(2026, 10, 12))

    assert len(bookings) == 1
    assert bookings[0].client_name == "Без имени"
    assert bookings[0].time == time(10, 15)


@pytest.mark.parametrize(
    "stored_phone",
    ["+79035523232", "89035523232", "9035523232", "+7 (903) 552-32-32"],
)
def test_find_client_matches_phone_in_any_format(stored_phone):
    api = FakeApi(found_clients=[FakeSdkClient("88", "Анна", stored_phone)])
    assert make_client(api).find_or_create_client("Анна", "+79035523232") == "88"


def test_find_client_returns_new_marker_when_phone_differs():
    api = FakeApi(found_clients=[FakeSdkClient("88", "Другая", "+79990000000")])
    assert make_client(api).find_or_create_client("Анна", "+79035523232") == NEW_CLIENT_ID


def test_sdk_errors_become_dikidi_unavailable():
    api = FakeApi()

    def boom(*args, **kwargs):
        raise ValueError("шлюз сменился")

    api.appointments.get_records = boom
    with pytest.raises(DikidiUnavailable):
        make_client(api).get_bookings_for_date(date(2026, 10, 12))


def test_save_without_journal_confirmation_is_not_success():
    api = FakeApi()
    api.appointments.save_appointment = lambda **kwargs: {}
    with pytest.raises(DikidiUnavailable):
        make_client(api).create_booking(0, "Анна", "+79035523232",
            [Service(id="11", title="услуга")], date(2026, 10, 12), time(15))
