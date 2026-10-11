import logging

from fastapi import FastAPI

from app.alice import router
from app.alice.models import AliceRequestBody, AliceResponseBody, AliceResponsePayload
from app.dikidi.client import DikidiUnavailable, get_dikidi_client

logger = logging.getLogger(__name__)

app = FastAPI(title="Dikidi Alice Skill")
_dikidi = get_dikidi_client()

UNAVAILABLE_TEXT = (
    "Не могу сейчас связаться с Dikidi. Попробуйте повторить через минуту."
)


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


@app.post("/alice/webhook", response_model=AliceResponseBody)
def alice_webhook(body: AliceRequestBody) -> AliceResponseBody:
    try:
        text, session_state = router.handle(body, _dikidi)
    except DikidiUnavailable:
        # Пятисотка в ответ Алисе выглядит как "Что-то пошло не так" и рвёт
        # диалог. Вместо этого говорим о проблеме и оставляем шаг сценария
        # как был, чтобы пользователь мог просто повторить фразу.
        logger.warning("Dikidi недоступна, отвечаю пользователю понятным текстом")
        text, session_state = UNAVAILABLE_TEXT, body.state.session

    return AliceResponseBody(
        response=AliceResponsePayload(text=text, tts=text, end_session=False),
        session_state=session_state,
        version=body.version,
    )
