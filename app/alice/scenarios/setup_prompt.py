"""Ответ навыка, когда аккаунт Dikidi ещё не привязан.

Пароль голосом не спрашиваем: произнесённое попадает в логи Яндекса и в тело
запроса к вебхуку. Вместо этого выдаём одноразовый код и отправляем вводить
данные на свою HTTPS-страницу /setup.
"""

from __future__ import annotations

from app.alice.models import AliceButton, AliceRequestBody
from app.pairing import codes


def handle(body: AliceRequestBody) -> tuple[str, dict, list[AliceButton] | None]:
    from app.config import settings

    user_id = body.session.user.get("user_id") or body.session.user_id
    if not settings.alice_owner_id or user_id != settings.alice_owner_id:
        return "Настройка доступна владельцу. Укажите ALICE_OWNER_ID в настройках сервера.", {}, None
    if not settings.public_base_url.startswith("https://"):
        return "Укажите PUBLIC_BASE_URL с HTTPS-адресом сервиса в настройках сервера.", {}, None
    code = codes.issue(user_id)
    spoken_code = " ".join(code)

    base_url = settings.public_base_url.rstrip("/")
    setup_url = f"{base_url}/setup" if base_url else "/setup"

    text = (
        "Чтобы я мог работать с вашим Dikidi, нужно один раз привязать аккаунт. "
        f"Откройте страницу {setup_url} и введите код {spoken_code}. "
        "Логин и пароль вводятся на странице, вслух их называть не нужно. "
        "Код действует десять минут. Когда закончите, скажите «добавь запись»."
    )

    buttons = [AliceButton(title="Открыть настройку", url=setup_url)] if base_url else None
    return text, {}, buttons
