import logging
from concurrent.futures import TimeoutError
from fastapi import FastAPI
from app.alice import router, session_store, jobs
from app.alice.models import AliceRequestBody, AliceResponseBody
from app.alice.responses import reply
from app.alice.scenarios import setup_prompt
from app.config import settings
from app.dikidi.client import DikidiUnavailable, BookingUncertain
from app.dikidi.provider import provider
from app.setup import setup_router

logger = logging.getLogger(__name__)
for name in ('DikidiAuth', 'DikidiTransport', 'DikidiTokenStorage',
             'DikidiAppointmentService', 'DikidiClientService'):
    logging.getLogger(name).disabled = True
app = FastAPI(title='Dikidi Alice Skill')
app.include_router(setup_router)
UNAVAILABLE_TEXT = 'Не могу сейчас связаться с Dikidi. Попробуйте повторить через минуту.'

@app.get('/')
def health() -> dict:
    return {'status': 'ok'}

def dispatch(body):
    try:
        client = provider.get()
        if client is None:
            return setup_prompt.handle(body)
        text, state = router.handle(body, client)
        if settings.dikidi_backend == 'mock':
            text = 'Демонстрационный режим, данные не отправляются в Dikidi. ' + text
        return text, state, None
    except BookingUncertain:
        session_store.put(body.session.session_id, {})
        return ('Не удалось подтвердить сохранение. Проверьте журнал Dikidi перед новой записью, чтобы не создать дубль.', {}, None)
    except DikidiUnavailable:
        logger.warning('Ошибка обращения к Dikidi')
        return UNAVAILABLE_TEXT, body.state.session or session_store.get(body.session.session_id), None
    except Exception as exc:
        logger.error('Ошибка обработки запроса (%s)', type(exc).__name__)
        return 'Не удалось обработать запрос. Попробуйте ещё раз.', body.state.session or session_store.get(body.session.session_id), None

@app.post('/alice/webhook', response_model=AliceResponseBody, response_model_exclude_none=True)
def alice_webhook(body: AliceRequestBody) -> AliceResponseBody:
    command = body.request.command.strip().lower()
    if command in ('проверка звука', 'проверь звук'):
        return reply('Проверка звука. Я озвучиваю ответы навыка.', body.state.session or session_store.get(body.session.session_id))
    user_id = body.session.user.get('user_id') or body.session.user_id
    if settings.alice_owner_id and user_id != settings.alice_owner_id:
        return reply('Этот навык доступен только владельцу салона.')
    if any(word in command for word in router.SETUP_KEYWORDS):
        return reply(*setup_prompt.handle(body))
    if settings.dikidi_backend == 'mock':
        return reply(*dispatch(body))
    if not body.session.session_id:
        return reply('Не удалось определить сессию. Откройте навык заново.')
    try:
        future = jobs.submit(body.session.session_id, body.session.message_id, lambda: dispatch(body))
    except RuntimeError:
        return reply('Сервис занят. Попробуйте через минуту.', body.state.session)
    try:
        result = future.result(timeout=2.0)
        future.delivered = True
        return reply(*result)
    except TimeoutError:
        return reply('Запрос к Dikidi ещё выполняется. Скажите «проверить результат» через несколько секунд.', body.state.session or session_store.get(body.session.session_id))
