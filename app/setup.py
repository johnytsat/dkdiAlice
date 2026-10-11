"""Настройка одного салона по одноразовому коду владельца."""
from html import escape
from urllib.parse import parse_qs
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app.credentials import DikidiCredentials, store
from app.dikidi.sdk_client import SdkDikidiClient
from app.pairing import codes, PairingError

setup_router = APIRouter()


def page(message="", status=200):
    return HTMLResponse('''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Подключение Dikidi</title><body><main>
<h1>Подключение Dikidi</h1><p>Введите код из навыка и данные своего салона.</p>
<p>''' + escape(message) + '''</p>
<form method="post" action="/setup">
<p><label>Код из Алисы <input name="code" pattern="[0-9]{6}" required autocomplete="off"></label></p>
<p><label>Телефон <input name="phone" type="tel" required autocomplete="username"></label></p>
<p><label>Пароль <input name="password" type="password" required autocomplete="current-password"></label></p>
<p><label>ID компании <input name="company_id" required pattern="[0-9]+"></label></p>
<p><label>ID мастера <input name="staff_id" required pattern="[0-9]+"></label></p>
<button>Проверить и подключить</button></form>
<p>Данные хранятся в памяти до перезапуска сервиса. Для постоянного подключения
задайте их в Environment на Render.</p></main></body></html>''', status_code=status,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                 "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'"})


@setup_router.get("/setup", response_class=HTMLResponse)
def setup_page():
    return page()


def connect(values):
    credentials = DikidiCredentials(phone=values["phone"].strip(), password=values["password"],
                                    company_id=values["company_id"].strip(),
                                    default_staff_id=values["staff_id"].strip())
    client = SdkDikidiClient(credentials.phone, credentials.password,
                           credentials.company_id, credentials.default_staff_id)
    try:
        client.list_services()
        masters = client._get_api().catalog.get_masters()
        if not any(str(m.id) == credentials.default_staff_id for m in masters):
            return False
    finally:
        if client._api is not None:
            client._api.close()
    store.set(credentials)
    return True


@setup_router.post("/setup", response_class=HTMLResponse)
async def save_setup(request: Request):
    if settings.dikidi_backend != "sdk" or not settings.alice_owner_id:
        return page("На сервере нужны DIKIDI_BACKEND=sdk и ALICE_OWNER_ID.", 403)
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.public_base_url.rstrip("/"):
        return page("Откройте страницу по ссылке из навыка.", 403)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            return page("Слишком большой запрос.", 413)
    try:
        form = parse_qs(raw.decode("utf-8"), max_num_fields=10)
        values = {k: form[k][0] for k in ("code", "phone", "password", "company_id", "staff_id")}
        owner = codes.verify(values["code"])
        if owner != settings.alice_owner_id:
            return page("Этот код не принадлежит владельцу.", 403)
    except (KeyError, ValueError, UnicodeError, PairingError):
        return page("Заполните все поля и запросите новый код у Алисы.", 400)
    try:
        connected = await run_in_threadpool(connect, values)
    except Exception:
        return page("Не удалось подключиться. Проверьте данные и доступ к Dikidi. Запросите новый код.", 400)
    if not connected:
        return page("Мастер не найден в компании. Проверьте ID и запросите новый код.", 400)
    return page("Аккаунт подключён. Вернитесь в Алису и скажите «добавь запись».")
