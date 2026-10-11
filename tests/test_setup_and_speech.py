from copy import deepcopy
from threading import Event
from fastapi.testclient import TestClient
from app.main import app
from app import main, setup
from app.config import settings
from app.alice import jobs, session_store
from app.pairing import codes
from tests.test_webhook_smoke import REALISTIC_PAYLOAD

client = TestClient(app)


def payload(command="", message=1):
    p = deepcopy(REALISTIC_PAYLOAD)
    p["request"]["command"] = command
    p["session"]["message_id"] = message
    p["session"]["user"] = {"user_id": "owner"}
    return p


def test_voice_response_has_tts_and_omits_null_buttons():
    r = client.post("/alice/webhook", json=payload("проверка звука")).json()
    assert "озвучиваю" in r["response"]["tts"]
    assert "buttons" not in r["response"]
    assert r["response"]["end_session"] is False


def test_setup_code_is_owner_only_and_one_use(monkeypatch):
    monkeypatch.setattr(settings, "dikidi_backend", "sdk")
    monkeypatch.setattr(settings, "alice_owner_id", "owner")
    monkeypatch.setattr(settings, "public_base_url", "https://example.onrender.com")
    codes.reset()
    calls = []
    monkeypatch.setattr(setup, "connect", lambda values: calls.append(values) or True)
    r = client.post("/alice/webhook", json=payload("настройка")).json()
    assert r["response"]["buttons"][0]["url"].endswith("/setup")
    code = next(iter(codes._codes))
    data = dict(code=code, phone="+70000000000", password="private", company_id="1", staff_id="2")
    r = client.post("/setup", data=data)
    assert r.status_code == 200
    assert "private" not in r.text
    assert r.headers["cache-control"] == "no-store"
    assert client.post("/setup", data=data).status_code == 400
    assert len(calls) == 1
    p = payload("настройка")
    p["session"]["user"]["user_id"] = "stranger"
    assert "только владельцу" in client.post("/alice/webhook", json=p).json()["response"]["text"]


def test_slow_booking_is_not_submitted_twice(monkeypatch):
    monkeypatch.setattr(settings, "dikidi_backend", "sdk")
    jobs._jobs.clear()
    release = Event()
    calls = []
    def slow(body):
        calls.append(body)
        assert release.wait(5)
        return "Записал", {}, None
    monkeypatch.setattr(main, "dispatch", slow)
    try:
        first = client.post("/alice/webhook", json=payload("да", 1)).json()
        assert "ещё выполняется" in first["response"]["tts"]
        release.set()
        second = client.post("/alice/webhook", json=payload("проверить результат", 2)).json()
        assert second["response"]["text"] == "Записал"
        repeated = client.post("/alice/webhook", json=payload("проверить результат", 2)).json()
        assert repeated == second
        assert len(calls) == 1
    finally:
        release.set()
        jobs._jobs.clear()


def test_error_keeps_server_side_state(monkeypatch):
    from app.dikidi.client import DikidiUnavailable
    state = {"scenario": "add_booking", "step": "ask_phone", "data": {}}
    session_store.put("session-1", state)
    def fail(*args):
        raise DikidiUnavailable()
    monkeypatch.setattr(main.router, "handle", fail)
    p = payload("Анна")
    p.pop("state")
    assert client.post("/alice/webhook", json=p).json()["session_state"] == state


def test_uncertain_save_does_not_offer_to_repeat_confirmation(monkeypatch):
    from app.dikidi.client import BookingUncertain
    def fail(*args):
        raise BookingUncertain()
    monkeypatch.setattr(main.router, "handle", fail)
    p = payload("да")
    p["state"] = {"session": {"step": "confirm"}}
    result = client.post("/alice/webhook", json=p).json()
    assert result["session_state"] == {}
    assert "Проверьте журнал" in result["response"]["text"]


def test_missing_credentials_prompts_for_setup(monkeypatch):
    from app.credentials import store, DikidiCredentials
    monkeypatch.setattr(settings, "dikidi_backend", "sdk")
    monkeypatch.setattr(settings, "alice_owner_id", "owner")
    monkeypatch.setattr(settings, "public_base_url", "https://example.onrender.com")
    monkeypatch.setattr(store, "get", lambda: DikidiCredentials())
    jobs._jobs.clear()
    result = client.post("/alice/webhook", json=payload()).json()
    assert "привязать аккаунт" in result["response"]["text"]
    assert result["response"]["tts"]
    jobs._jobs.clear()
