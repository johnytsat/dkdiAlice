from datetime import date, time, timedelta

from app.alice import router
from tests.conftest import build_request


def test_no_bookings_today(dikidi):
    text, state = router.handle(build_request("сколько человек записано на сегодня"), dikidi)
    assert state == {}
    assert "записей нет" in text.lower()


def test_counts_and_lists_bookings_today(dikidi):
    service = dikidi.list_services()[0]
    client_id = dikidi.find_or_create_client("Иван", "+79991234567")
    dikidi.create_booking(client_id, "Иван", "+79991234567", [service], date.today(), time(10, 0))
    dikidi.create_booking(client_id, "Пётр", "+79997654321", [service], date.today(), time(14, 30))

    text, state = router.handle(build_request("сколько записей на сегодня"), dikidi)
    assert state == {}
    assert "2 записи" in text.lower()
    assert "10:00" in text
    assert "14:30" in text


def test_bookings_for_tomorrow_via_datetime_entity(dikidi):
    service = dikidi.list_services()[0]
    client_id = dikidi.find_or_create_client("Иван", "+79991234567")
    tomorrow = date.today() + timedelta(days=1)
    dikidi.create_booking(client_id, "Иван", "+79991234567", [service], tomorrow, time(9, 0))

    entities = [{"type": "YANDEX.DATETIME", "value": {"day": 1, "day_is_relative": True}}]
    text, state = router.handle(
        build_request("а сколько записей завтра", entities=entities), dikidi
    )
    assert state == {}
    assert "1 запись" in text.lower()
    assert "09:00" in text
