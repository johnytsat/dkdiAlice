from datetime import datetime

from app.alice import nlu
from app.alice.models import NluEntity
from app.dikidi.models import Service

SERVICES = [
    Service(id=1, title="маникюр"),
    Service(id=2, title="педикюр"),
    Service(id=3, title="стрижка"),
]


def test_extract_phone_with_8_prefix():
    assert nlu.extract_phone("мой телефон 89991234567") == "+79991234567"


def test_extract_phone_with_spaces():
    assert nlu.extract_phone("номер 8 999 123 45 67") == "+79991234567"


def test_extract_phone_missing():
    assert nlu.extract_phone("без телефона") is None


def test_extract_name_skips_trigger_words():
    assert nlu.extract_name("Добавь запись Ивану на маникюр") == "Ивану"


def test_extract_name_none_when_no_candidates():
    assert nlu.extract_name("добавь запись на маникюр") is None


def test_clean_name_fallback_strips_lead_in():
    assert nlu.clean_name_fallback("зовут иван") == "Иван"


def test_extract_service_exact_substring():
    service = nlu.extract_service("хочу записаться на маникюр", SERVICES)
    assert service is not None
    assert service.title == "маникюр"


def test_extract_service_fuzzy_match():
    service = nlu.extract_service("запишите на стрижку", SERVICES)
    assert service is not None
    assert service.title == "стрижка"


def test_extract_service_no_match():
    assert nlu.extract_service("просто поговорить", SERVICES) is None


def test_extract_datetime_relative_day_and_absolute_time():
    now = datetime(2026, 10, 11, 12, 0, 0)
    entities = [
        NluEntity(
            type="YANDEX.DATETIME",
            value={
                "day": 1,
                "day_is_relative": True,
                "hour": 15,
                "hour_is_relative": False,
                "minute": 0,
                "minute_is_relative": False,
            },
        )
    ]
    d, t = nlu.extract_datetime(entities, now)
    assert d.isoformat() == "2026-10-12"
    assert t.strftime("%H:%M") == "15:00"


def test_extract_datetime_no_entities():
    now = datetime(2026, 10, 11, 12, 0, 0)
    d, t = nlu.extract_datetime([], now)
    assert d is None
    assert t is None
