"""Эвристики извлечения слотов из реплики пользователя Алисы.

Дата/время парсятся из сущностей YANDEX.DATETIME, которые Алиса распознаёт
автоматически (без настройки форм в консоли). Телефон и услуга — через
регулярки/нечёткое сопоставление по тексту. Имя — упрощённая эвристика
(первое "похожее на имя" слово); для составных имён/фамилий может
потребоваться ручная правка через команду "исправить имя".
"""

from __future__ import annotations

import difflib
import re
from datetime import date, datetime, time, timedelta

from app.alice.models import NluEntity
from app.dikidi.models import Service

PHONE_RE = re.compile(r"(?:\+?7|8)?[\s\-]?\(?(\d{3})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})\b")

NAME_STOPWORDS = {
    "добавь", "запиши", "запись", "записать", "клиента", "клиент",
    "здравствуй", "привет", "алиса",
}

LEAD_IN_RE = re.compile(r"^(её зовут|его зовут|зовут|имя клиента|имя)\s+", re.IGNORECASE)

SERVICE_MATCH_THRESHOLD = 0.72


def extract_phone(text: str) -> str | None:
    match = PHONE_RE.search(text)
    if not match:
        return None
    return "+7" + "".join(match.groups())


def extract_name_from_entities(entities: list[NluEntity]) -> str | None:
    for entity in entities:
        if entity.type != "YANDEX.FIO" or not isinstance(entity.value, dict):
            continue
        parts = [entity.value.get("first_name"), entity.value.get("last_name")]
        name = " ".join(part.capitalize() for part in parts if part)
        if name:
            return name
    return None


def extract_name(text: str) -> str | None:
    words = re.findall(r"[А-ЯЁ][а-яё]+", text)
    candidates = [w for w in words if w.lower() not in NAME_STOPWORDS]
    return candidates[0] if candidates else None


def clean_name_fallback(text: str) -> str | None:
    cleaned = LEAD_IN_RE.sub("", text.strip())
    cleaned = cleaned.strip(" .,!?")
    if not cleaned:
        return None
    return " ".join(word.capitalize() for word in cleaned.split())


def extract_service(text: str, services: list[Service]) -> Service | None:
    text_lower = text.lower()
    for service in services:
        if service.title.lower() in text_lower:
            return service

    words = text_lower.split()
    best: Service | None = None
    best_ratio = 0.0
    for service in services:
        title = service.title.lower()
        for n in (1, 2, 3):
            for i in range(max(len(words) - n + 1, 0)):
                phrase = " ".join(words[i : i + n])
                ratio = difflib.SequenceMatcher(None, phrase, title).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = service
    return best if best_ratio >= SERVICE_MATCH_THRESHOLD else None


def _resolve_date(value: dict, now: datetime) -> date | None:
    if value.get("day") is None and value.get("month") is None and value.get("year") is None:
        return None
    if value.get("day_is_relative"):
        return (now + timedelta(days=value.get("day", 0))).date()
    day = value.get("day") if value.get("day") is not None else now.day
    month = value.get("month") if value.get("month") is not None else now.month
    year = value.get("year") if value.get("year") is not None else now.year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_time(value: dict, now: datetime) -> time | None:
    if value.get("hour") is None and value.get("minute") is None:
        return None
    if value.get("hour_is_relative") or value.get("minute_is_relative"):
        delta = timedelta(hours=value.get("hour") or 0, minutes=value.get("minute") or 0)
        return (now + delta).time().replace(second=0, microsecond=0)
    hour = value.get("hour") if value.get("hour") is not None else 0
    minute = value.get("minute") if value.get("minute") is not None else 0
    return time(hour=hour, minute=minute)


def extract_datetime(entities: list[NluEntity], now: datetime) -> tuple[date | None, time | None]:
    result_date: date | None = None
    result_time: time | None = None
    for entity in entities:
        if entity.type != "YANDEX.DATETIME" or not isinstance(entity.value, dict):
            continue
        if result_date is None:
            result_date = _resolve_date(entity.value, now)
        if result_time is None:
            result_time = _resolve_time(entity.value, now)
    return result_date, result_time
