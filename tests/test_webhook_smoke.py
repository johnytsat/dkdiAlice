from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

REALISTIC_PAYLOAD = {
    "meta": {"locale": "ru-RU", "timezone": "Europe/Moscow", "client_id": "test"},
    "request": {
        "command": "добавь запись",
        "original_utterance": "Добавь запись",
        "type": "SimpleUtterance",
        "nlu": {"tokens": ["добавь", "запись"], "entities": []},
    },
    "session": {
        "new": True,
        "message_id": 0,
        "session_id": "session-1",
        "skill_id": "skill-1",
        "user_id": "user-1",
        "application": {"application_id": "app-1"},
    },
    "state": {"session": {}},
    "version": "1.0",
}


def test_webhook_accepts_realistic_alice_payload():
    response = client.post("/alice/webhook", json=REALISTIC_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.0"
    assert "зовут" in data["response"]["text"].lower()
    assert data["session_state"]["step"] == "ask_name"
