"""Browser login: two fields, automatic linking and named choices."""
from html import escape
import secrets
import time
from threading import Lock, RLock
from urllib.parse import parse_qs, urlsplit
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app.credentials import DikidiCredentials, store
from app.dikidi.discovery import Discovery, DiscoveryError
from app.pairing import codes, PairingError

setup_router = APIRouter()
_sessions = {}
_lock = Lock()
COOKIE = 'dikidi_setup'
logger = logging.getLogger(__name__)

class Session:
    def __init__(self, owner):
        self.owner = owner
        self.csrf = secrets.token_urlsafe(32)
        self.expires = time.monotonic() + 600
        self.discovery = None
        self.company = ''
        self.masters = {}
        self.attempts = 0
        self.stage = 'storage'
        self.lock = RLock()
    def close(self):
        if self.discovery:
            self.discovery.close()
        self.discovery = None


def get_session(request):
    with _lock:
        for token, session in list(_sessions.items()):
            if session.expires < time.monotonic() and session.lock.acquire(blocking=False):
                try:
                    session.close()
                    del _sessions[token]
                finally:
                    session.lock.release()
        return _sessions.get(request.cookies.get(COOKIE, ''))


def page(message='', session=None, choices=None, action='login', status=200):
    nonce = secrets.token_urlsafe(16)
    form = ''
    if session:
        if choices:
            fields = '<label>Выберите ' + ('салон' if action == 'company' else 'мастера') + '<select name="choice">'
            fields += ''.join('<option value="' + escape(k, quote=True) + '">' + escape(v) + '</option>' for k, v in choices.items())
            fields += '</select></label>'
        else:
            fields = '<label>Телефон DIKIDI<input name="phone" type="tel" autocomplete="username" required></label><label>Пароль<input name="password" type="password" autocomplete="current-password" required></label>'
        form = '<form method="post" action="/setup"><input type="hidden" name="csrf" value="' + session.csrf + '"><input type="hidden" name="action" value="' + action + '">' + fields + '<button>Продолжить</button></form>'
    # Fragment is never sent in the URL/access log. Exchange it for an HttpOnly cookie.
    script = '''if(location.hash){const token=location.hash.slice(1);history.replaceState(null,'','/setup');fetch('/setup/exchange',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({token})}).then(r=>{if(r.ok)location.replace('/setup');else document.getElementById('message').textContent='Ссылка истекла. Скажите Алисе «настройка» ещё раз.';});}'''
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Подключение DIKIDI</title>'
    html += '<style nonce="' + nonce + '">body{font:18px system-ui;background:#f4f6fa;color:#172135;margin:0}main{max-width:420px;margin:8vh auto;padding:32px;background:white;border-radius:20px}label{display:block;margin:20px 0}input,select,button{display:block;box-sizing:border-box;width:100%;font:inherit;padding:12px;margin-top:8px}button{background:#5147db;color:white;border:0;border-radius:10px;cursor:pointer}p{line-height:1.5}</style>'
    html += '<main><h1>Подключение DIKIDI</h1><p id="message">' + escape(message) + '</p>' + form + '</main><script nonce="' + nonce + '">' + script + '</script></html>'
    return HTMLResponse(html, status_code=status, headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer', 'Content-Security-Policy':f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})


def url_origin(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Origin')
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)


async def form_data(request, allow_opaque_origin=False):
    origin = request.headers.get('origin')
    # Some embedded browsers send an opaque Origin. Only the session-bound
    # form may accept it: advance still requires the secret CSRF token.
    if origin and not (origin == 'null' and allow_opaque_origin):
        if url_origin(origin) != url_origin(settings.public_base_url):
            raise ValueError('Origin')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise ValueError('Body too large')
    parsed = parse_qs(raw.decode(), max_num_fields=8)
    if any(len(v) != 1 for v in parsed.values()):
        raise ValueError('Duplicate field')
    return {k: v[0] for k, v in parsed.items()}


@setup_router.post('/setup/exchange')
async def exchange(request: Request):
    try:
        form = await form_data(request)
        owner = codes.verify(form.get('token', ''))
        current = await run_in_threadpool(store.get)
        if current.owner_id and current.owner_id != owner:
            raise PairingError('Wrong owner')
        get_session(request)
        with _lock:
            if len(_sessions) >= 200:
                raise PairingError('Busy')
            token = secrets.token_urlsafe(32)
            _sessions[token] = Session(owner)
        response = Response(status_code=204, headers={'Cache-Control':'no-store'})
        response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite='strict', max_age=600, path='/setup')
        return response
    except (ValueError, PairingError):
        return Response(status_code=403)
    except Exception:
        return Response(status_code=503)


@setup_router.get('/setup', response_class=HTMLResponse)
def setup_page(request: Request):
    session = get_session(request)
    if not session:
        return page('Откройте ссылку из навыка Алисы — скажите «настройка».')
    with session.lock:
        if session.discovery and session.company:
            return page('Выберите мастера для новых записей.', session, session.masters, 'staff')
        if session.discovery:
            return page('Выберите ваш салон.', session, session.discovery.companies, 'company')
        return page('Введите телефон и пароль от DIKIDI Business.', session)


def finish(session, staff):
    session.stage = 'save'
    discovery = session.discovery
    store.set(DikidiCredentials(phone=discovery.phone, password=discovery.password,
              company_id=session.company, default_staff_id=staff, owner_id=session.owner))
    session.close()
    session.expires = 0
    response = page('Готово! Аккаунт подключён. Вернитесь в Алису и скажите «добавь запись».')
    response.delete_cookie(COOKIE, path='/setup')
    return response


def choose_company(session, company):
    session.stage = 'masters'
    if company not in session.discovery.companies:
        raise ValueError('Unknown company')
    masters = session.discovery.masters(company)
    if not masters:
        raise ValueError('No masters')
    session.company, session.masters = company, masters
    if len(masters) == 1:
        return finish(session, next(iter(masters)))
    return page('Выберите мастера для новых записей.', session, masters, 'staff')


def advance(session, form):
    with session.lock:
        if session.expires < time.monotonic() or not secrets.compare_digest(form.get('csrf',''), session.csrf):
            return page('Откройте новую ссылку из Алисы.', status=403)
        if settings.dikidi_backend != 'sdk':
            return page('Подключение временно недоступно.', status=503)
        try:
            session.stage = 'storage'
            store.database()  # Fail before accepting passwords if durable storage isn't ready.
            current = store.get()
            if current.owner_id and current.owner_id != session.owner:
                return page('Аккаунт уже подключён другим пользователем.', status=403)
            action = form.get('action')
            if action == 'login':
                session.attempts += 1
                if session.attempts > 3:
                    session.close()
                    session.expires = 0
                    return page('Слишком много попыток. Получите новую ссылку у Алисы.', status=429)
                session.close()
                session.company, session.masters = '', {}
                session.stage = 'authentication'
                session.discovery = Discovery(form['phone'].strip(), form['password'])
                companies = session.discovery.login()
                if len(companies) == 1:
                    return choose_company(session, next(iter(companies)))
                return page('Выберите ваш салон.', session, companies, 'company')
            if action == 'company' and session.discovery:
                return choose_company(session, form.get('choice'))
            if action == 'staff' and form.get('choice') in session.masters:
                return finish(session, form['choice'])
            raise ValueError('Invalid step')
        except Exception as exc:
            stage = exc.stage if isinstance(exc, DiscoveryError) else session.stage
            # Never log exception messages/responses: SDK errors may contain credentials.
            cause = exc.__cause__ or exc
            logger.warning('DIKIDI setup failed: stage=%s type=%s', stage, type(cause).__name__)
            session.close()
            session.company, session.masters = '', {}
            messages = {
                'storage': 'Не удалось открыть защищённое хранилище. Администратору нужно проверить базу и ключ шифрования.',
                'authentication': 'Не удалось завершить вход через DIKIDI. Это может быть ограничение автоматического входа или изменение страницы авторизации, а не неверный пароль.',
                'companies': 'Не удалось получить список салонов после входа. Требуется исправить чтение кабинета DIKIDI; повторный ввод пароля не решит эту ошибку.',
                'masters': 'Не удалось получить мастеров выбранного салона. Проверьте доступ к сотрудникам в DIKIDI Business.',
                'save': 'Не удалось сохранить подключение в базе. Администратору нужно проверить хранилище.',
            }
            message = messages.get(stage, 'Не удалось завершить подключение.')
            return page(message + ' Код ошибки: ' + stage + '.', session, status=400)


@setup_router.post('/setup', response_class=HTMLResponse)
async def save_setup(request: Request):
    session = get_session(request)
    if not session:
        return page('Ссылка истекла. Скажите Алисе «настройка».', status=403)
    try:
        form = await form_data(request, allow_opaque_origin=True)
    except (ValueError, UnicodeError) as exc:
        reason = str(exc) if str(exc) in ('Origin', 'Body too large', 'Duplicate field') else 'Invalid encoding or fields'
        logger.warning('Setup form rejected: %s', reason)
        message = ('Адрес страницы не совпадает с настройкой сервера. Администратору нужно проверить PUBLIC_BASE_URL. Откройте новую ссылку из Алисы.'
                   if reason == 'Origin' else 'Не удалось прочитать форму. Откройте новую ссылку из Алисы и повторите ввод.')
        return page(message, status=400)
    return await run_in_threadpool(advance, session, form)
