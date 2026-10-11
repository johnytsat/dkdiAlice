"""Клиенты Алисы, которые не возвращают state (например, поиск Яндекса на Android),
должны всё равно проходить диалог — состояние берётся из серверного хранилища.
"""

from datetime import date, timedelta

from app.alice import router
from tests.conftest import build_request

FIO_ANNA = [{"type": "YANDEX.FIO", "value": {"first_name": "анна"}}]


def test_dialog_advances_without_state_echo(dikidi):
    text, _ = router.handle(
        build_request("добавь запись", new=True, include_state=False), dikidi
    )
    assert "зовут" in text.lower()

    text, _ = router.handle(
        build_request("анна", original="Анна", entities=FIO_ANNA, include_state=False),
        dikidi,
    )
    assert "телефон" in text.lower()

    text, _ = router.handle(build_request("89991234567", include_state=False), dikidi)
    assert "услуг" in text.lower()


def test_full_booking_without_state_echo(dikidi):
    router.handle(build_request("добавь запись", new=True, include_state=False), dikidi)
    router.handle(
        build_request("анна", original="Анна", entities=FIO_ANNA, include_state=False), dikidi
    )
    router.handle(build_request("89991234567", include_state=False), dikidi)
    router.handle(build_request("маникюр", include_state=False), dikidi)
    router.handle(
        build_request(
            "завтра",
            entities=[{"type": "YANDEX.DATETIME", "value": {"day": 1, "day_is_relative": True}}],
            include_state=False,
        ),
        dikidi,
    )
    text, _ = router.handle(
        build_request(
            "в 15:00",
            entities=[
                {
                    "type": "YANDEX.DATETIME",
                    "value": {
                        "hour": 15,
                        "hour_is_relative": False,
                        "minute": 0,
                        "minute_is_relative": False,
                    },
                }
            ],
            include_state=False,
        ),
        dikidi,
    )
    assert "анна" in text.lower()
    assert "всё верно" in text.lower()

    text, _ = router.handle(build_request("да", include_state=False), dikidi)
    assert "записал" in text.lower()

    bookings = dikidi.get_bookings_for_date(date.today() + timedelta(days=1))
    assert len(bookings) == 1
    assert bookings[0].client_name == "Анна"


def test_separate_sessions_do_not_share_state(dikidi):
    router.handle(
        build_request("добавь запись", new=True, include_state=False, session_id="session-a"),
        dikidi,
    )
    text, _ = router.handle(
        build_request("сколько записей на сегодня", include_state=False, session_id="session-b"),
        dikidi,
    )
    assert "записей нет" in text.lower()
