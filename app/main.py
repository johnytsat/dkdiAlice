from fastapi import FastAPI

from app.alice import router
from app.alice.models import AliceRequestBody, AliceResponseBody, AliceResponsePayload
from app.dikidi.client import get_dikidi_client

app = FastAPI(title="Dikidi Alice Skill")
_dikidi = get_dikidi_client()


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


@app.post("/alice/webhook", response_model=AliceResponseBody)
def alice_webhook(body: AliceRequestBody) -> AliceResponseBody:
    text, session_state = router.handle(body, _dikidi)
    return AliceResponseBody(
        response=AliceResponsePayload(text=text, tts=text, end_session=False),
        session_state=session_state,
        version=body.version,
    )
