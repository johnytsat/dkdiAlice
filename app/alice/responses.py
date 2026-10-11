import re

from app.alice.models import AliceResponseBody, AliceResponsePayload


def reply(text, state=None, buttons=None):
    # Каталог и имена могут содержать символы разметки TTS.
    text = text[:1024]
    speech = re.sub(r"https?://\S+", "по ссылке на экране", text)
    speech = speech.replace("Dikidi", "Дикиди").replace("DIKIDI", "Дикиди")
    speech = re.sub(r"[<>+\[\]{}]", " ", speech)
    return AliceResponseBody(
        response=AliceResponsePayload(text=text, tts=speech[:1024],
                                      buttons=buttons, end_session=False),
        session_state=state or {},
    )
