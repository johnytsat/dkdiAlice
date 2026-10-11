from datetime import date, timedelta

from app.alice import router
from tests.conftest import build_request

TOMORROW_ENTITY = {"type": "YANDEX.DATETIME", "value": {"day": 1, "day_is_relative": True}}
TIME_15_ENTITY = {
    "type": "YANDEX.DATETIME",
    "value": {"hour": 15, "hour_is_relative": False, "minute": 0, "minute_is_relative": False},
}


def _walk_to_confirm(dikidi, service_words=("маникюр",)):
    """Проходит диалог до шага подтверждения, возвращает (text, state)."""
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)
    for word in service_words:
        _, state = router.handle(build_request(word, state=state), dikidi)
    _, state = router.handle(build_request("всё", state=state), dikidi)
    _, state = router.handle(
        build_request("завтра", state=state, entities=[TOMORROW_ENTITY]), dikidi
    )
    return router.handle(build_request("в 15:00", state=state, entities=[TIME_15_ENTITY]), dikidi)


def test_full_add_booking_dialog(dikidi):
    text, state = router.handle(build_request("добавь запись", new=True), dikidi)
    assert state["step"] == "ask_name"
    assert "зовут" in text.lower()

    text, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    assert state["step"] == "ask_phone"

    text, state = router.handle(build_request("89991234567", state=state), dikidi)
    assert state["step"] == "ask_services"

    text, state = router.handle(build_request("маникюр", state=state), dikidi)
    assert state["step"] == "ask_services"
    assert "добавил маникюр" in text.lower()

    text, state = router.handle(build_request("всё", state=state), dikidi)
    assert state["step"] == "ask_date"

    text, state = router.handle(
        build_request("завтра", state=state, entities=[TOMORROW_ENTITY]), dikidi
    )
    assert state["step"] == "ask_time"

    text, state = router.handle(
        build_request("в 15:00", state=state, entities=[TIME_15_ENTITY]), dikidi
    )
    assert state["step"] == "confirm"
    assert "иван" in text.lower()
    assert "маникюр" in text.lower()

    text, state = router.handle(build_request("да", state=state), dikidi)
    assert state == {}
    assert "записал" in text.lower()

    bookings = dikidi.get_bookings_for_date(date.today() + timedelta(days=1))
    assert len(bookings) == 1
    assert bookings[0].client_phone == "+79991234567"
    assert bookings[0].service_titles == ["маникюр"]


def test_multiple_services_collected_until_done(dikidi):
    text, state = _walk_to_confirm(dikidi, service_words=("руки полностью", "живот"))
    assert state["step"] == "confirm"
    assert "руки полностью" in text.lower()
    assert "живот" in text.lower()

    text, state = router.handle(build_request("да", state=state), dikidi)
    bookings = dikidi.get_bookings_for_date(date.today() + timedelta(days=1))
    assert bookings[0].service_titles == ["руки полностью", "живот"]


def test_stop_during_service_listing_finishes_list_not_booking(dikidi):
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)
    _, state = router.handle(build_request("живот", state=state), dikidi)

    text, state = router.handle(build_request("стоп", state=state), dikidi)
    assert state.get("scenario") == "add_booking"
    assert state["step"] == "ask_date"
    assert "дат" in text.lower()


def test_unknown_service_explains_and_lists_catalog(dikidi):
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)

    text, state = router.handle(build_request("полет на луну", state=state), dikidi)
    assert state["step"] == "ask_services"
    assert "не нашёл" in text.lower()
    assert "доступны" in text.lower()
    assert not state["data"].get("services")


def test_duplicate_service_not_added_twice(dikidi):
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)
    _, state = router.handle(build_request("живот", state=state), dikidi)

    text, state = router.handle(build_request("живот", state=state), dikidi)
    assert "уже в списке" in text.lower()
    assert len(state["data"]["services"]) == 1


def test_done_with_no_services_asks_again(dikidi):
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)

    text, state = router.handle(build_request("хватит", state=state), dikidi)
    assert state["step"] == "ask_services"
    assert "хотя бы одна услуга" in text.lower()


def test_add_booking_single_utterance_prefills_and_asks_for_more_services(dikidi):
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
    assert state["step"] == "ask_services"
    assert state["data"]["name"] == "Ивану"
    assert state["data"]["phone"] == "+79991234567"
    assert [item["title"] for item in state["data"]["services"]] == ["маникюр"]
    assert "пока записал" in text.lower()

    text, state = router.handle(build_request("всё", state=state), dikidi)
    assert state["step"] == "confirm"


def test_cancel_clears_scenario(dikidi):
    text, state = router.handle(build_request("добавь запись", new=True), dikidi)
    assert state["step"] == "ask_name"

    text, state = router.handle(build_request("отмена", state=state), dikidi)
    assert state == {}
    assert "не создаю" in text.lower()


def test_cancel_during_service_listing_with_nothing_collected(dikidi):
    _, state = router.handle(build_request("добавь запись", new=True), dikidi)
    _, state = router.handle(build_request("иван", original="Иван", state=state), dikidi)
    _, state = router.handle(build_request("89991234567", state=state), dikidi)

    text, state = router.handle(build_request("отмена", state=state), dikidi)
    assert state == {}
    assert "не создаю" in text.lower()


def test_confirm_no_routes_to_correct(dikidi):
    _, state = _walk_to_confirm(dikidi)
    assert state["step"] == "confirm"

    text, state = router.handle(build_request("нет", state=state), dikidi)
    assert state["step"] == "correct"

    text, state = router.handle(build_request("телефон", state=state), dikidi)
    assert state["step"] == "ask_phone"
    assert "phone" not in state["data"]


def test_correcting_services_restarts_listing(dikidi):
    _, state = _walk_to_confirm(dikidi)
    _, state = router.handle(build_request("нет", state=state), dikidi)

    text, state = router.handle(build_request("услуги", state=state), dikidi)
    assert state["step"] == "ask_services"
    assert not state["data"].get("services")
    assert not state["data"].get("services_confirmed")
