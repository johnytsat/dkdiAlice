from datetime import date, timedelta

from app.alice import router
from tests.conftest import build_request


def test_full_add_booking_dialog(dikidi):
    text, state = router.handle(build_request("добавь запись", new=True), dikidi)
    assert state["step"] == "ask_name"
    assert "зовут" in text.lower()

    text, state = router.handle(
        build_request("иван", original="Иван", state=state), dikidi
    )
    assert state["step"] == "ask_phone"

    text, state = router.handle(
        build_request("89991234567", state=state), dikidi
    )
    assert state["step"] == "ask_service"

    text, state = router.handle(
        build_request("маникюр", state=state), dikidi
    )
    assert state["step"] == "ask_date"

    tomorrow_entity = {
        "type": "YANDEX.DATETIME",
        "value": {"day": 1, "day_is_relative": True},
    }
    text, state = router.handle(
        build_request("завтра", state=state, entities=[tomorrow_entity]), dikidi
    )
    assert state["step"] == "ask_time"

    time_entity = {
        "type": "YANDEX.DATETIME",
        "value": {"hour": 15, "hour_is_relative": False, "minute": 0, "minute_is_relative": False},
    }
    text, state = router.handle(
        build_request("в 15:00", state=state, entities=[time_entity]), dikidi
    )
    assert state["step"] == "confirm"
    assert "иван" in text.lower()
    assert "маникюр" in text.lower()

    text, state = router.handle(build_request("да", state=state), dikidi)
    assert state == {}
    assert "записал" in text.lower()

    tomorrow = date.today() + timedelta(days=1)
    bookings = dikidi.get_bookings_for_date(tomorrow)
    assert len(bookings) == 1
    assert bookings[0].client_phone == "+79991234567"
    assert bookings[0].service_title == "маникюр"


def test_add_booking_single_utterance_collects_all_slots(dikidi):
    entities = [
        {
            "type": "YANDEX.DATETIME",
            "value": {
                "day": 1,
                "day_is_relative": True,
                "hour": 10,
                "hour_is_relative": False,
                "minute": 30,
                "minute_is_relative": False,
            },
        }
    ]
    text, state = router.handle(
        build_request(
            "добавь запись на маникюр телефон 89991234567",
            original="Добавь запись Ивану на маникюр телефон 89991234567",
            entities=entities,
            new=True,
        ),
        dikidi,
    )
    assert state["step"] == "confirm"
    assert state["data"]["name"] == "Ивану"
    assert state["data"]["phone"] == "+79991234567"
    assert state["data"]["service_title"] == "маникюр"


def test_cancel_clears_scenario(dikidi):
    text, state = router.handle(build_request("добавь запись", new=True), dikidi)
    assert state["step"] == "ask_name"

    text, state = router.handle(build_request("отмена", state=state), dikidi)
    assert state == {}
    assert "не создаю" in text.lower()


def test_confirm_no_routes_to_correct(dikidi):
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)
    _, state = router.handle(build_request("маникюр", state=state), dikidi)
    _, state = router.handle(
        build_request(
            "завтра",
            state=state,
            entities=[{"type": "YANDEX.DATETIME", "value": {"day": 1, "day_is_relative": True}}],
        ),
        dikidi,
    )
    _, state = router.handle(
        build_request(
            "в 15:00",
            state=state,
            entities=[
                {
                    "type": "YANDEX.DATETIME",
                    "value": {"hour": 15, "hour_is_relative": False, "minute": 0, "minute_is_relative": False},
                }
            ],
        ),
        dikidi,
    )
    assert state["step"] == "confirm"

    text, state = router.handle(build_request("нет", state=state), dikidi)
    assert state["step"] == "correct"

    text, state = router.handle(build_request("телефон", state=state), dikidi)
    assert state["step"] == "ask_phone"
    assert "phone" not in state["data"]
