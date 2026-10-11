import re
from dataclasses import asdict
from urllib.parse import urlparse
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import InvalidToken
from app.main import app
from app import setup
from app.config import settings
from app.credentials import store, CredentialStore, DikidiCredentials
from app.credential_db import ConnectionDB
from app.pairing import codes
from app.alice import jobs
from app.dikidi.discovery import parse_companies
from tests.test_setup_and_speech import payload


class FakeDiscovery:
    companies_template = {"1": "Салон Анны"}
    masters_template = {"7": "Анна"}

    def __init__(self, phone, password):
        self.phone, self.password = phone, password
        self.companies = dict(self.companies_template)
    def login(self):
        return self.companies
    def masters(self, company):
        assert company in self.companies
        return dict(self.masters_template)
    def close(self):
        self.password = ""


@pytest.fixture
def browser(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + (tmp_path / "connections.db").as_posix())
    monkeypatch.setattr(settings, "credentials_encryption_key", "testing-secret-key-" * 3)
    monkeypatch.setattr(settings, "dikidi_backend", "sdk")
    monkeypatch.setattr(settings, "alice_owner_id", "")
    for key in ("dikidi_phone", "dikidi_password", "dikidi_company_id"):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "public_base_url", "https://testserver")
    monkeypatch.setattr(store, "_db", None)
    monkeypatch.setattr(store, "_credentials", None)
    monkeypatch.setattr(setup, "Discovery", FakeDiscovery)
    jobs._jobs.clear()
    codes.reset()
    setup._sessions.clear()
    with TestClient(app, base_url="https://testserver") as client:
        yield client
    for session in setup._sessions.values():
        session.close()
    setup._sessions.clear()
    jobs._jobs.clear()
    if store._db:
        store._db.engine.dispose()


def open_login(browser, user="owner"):
    p = payload("настройка")
    p["session"]["user"]["user_id"] = user
    p["session"]["session_id"] = "setup-" + user
    response = browser.post("/alice/webhook", json=p).json()
    url = response["response"]["buttons"][0]["url"]
    token = urlparse(url).fragment
    assert len(token) >= 40
    assert token not in response["response"]["tts"]
    assert browser.post("/setup/exchange", data={"token": token}).status_code == 204
    assert browser.post("/setup/exchange", data={"token": token}).status_code == 403
    html = browser.get("/setup").text
    assert 'name="company_id"' not in html
    assert 'name="code"' not in html
    return re.search('name="csrf" value="([^"]+)"', html)[1]


def login(browser, csrf):
    return browser.post("/setup", data={"action": "login", "csrf": csrf,
                                         "phone": "+70000000000", "password": "hidden-password"})


def test_two_fields_auto_select_and_restore(browser):
    csrf = open_login(browser)
    response = login(browser, csrf)
    assert "Готово" in response.text
    assert "hidden-password" not in response.text
    saved = CredentialStore().get()
    assert (saved.company_id, saved.default_staff_id, saved.owner_id) == ("1", "7", "owner")
    assert saved.password == "hidden-password"
    other = payload("сколько записей сегодня", 2)
    other["session"]["user"]["user_id"] = "other"
    other["session"]["session_id"] = "other-session"
    assert "только владельцу" in browser.post("/alice/webhook", json=other).json()["response"]["text"]


def test_multiple_choices_by_name(browser, monkeypatch):
    monkeypatch.setattr(FakeDiscovery, "companies_template", {"1": "Салон А", "2": "Салон Б"})
    monkeypatch.setattr(FakeDiscovery, "masters_template", {"7": "Анна", "8": "Мария"})
    csrf = open_login(browser)
    r = login(browser, csrf)
    assert "Салон Б" in r.text and 'name="choice"' in r.text
    assert not store.get().is_complete
    r = browser.post("/setup", data={"action":"company", "choice":"2", "csrf":csrf})
    assert "Мария" in r.text
    r = browser.post("/setup", data={"action":"staff", "choice":"8", "csrf":csrf})
    assert "Готово" in r.text
    assert store.get().default_staff_id == "8"
    assert store.get().company_id == "2"


def test_csrf_and_unlisted_company_rejected(browser, monkeypatch):
    monkeypatch.setattr(FakeDiscovery, "companies_template", {"1":"А", "2":"Б"})
    csrf = open_login(browser)
    assert login(browser, "wrong").status_code == 403
    login(browser, csrf)
    r = browser.post("/setup", data={"action":"company", "choice":"999", "csrf":csrf})
    assert r.status_code == 400
    assert not store.get().is_complete


def test_failed_login_does_not_replace_saved_connection(browser, monkeypatch):
    store.set(DikidiCredentials("phone", "previous", "1", "7", "owner"))
    def fail(self):
        raise ValueError("private details")
    monkeypatch.setattr(FakeDiscovery, "login", fail)
    csrf = open_login(browser)
    response = login(browser, csrf)
    assert response.status_code == 400
    assert "private details" not in response.text
    assert store.get().password == "previous"


def test_database_encrypted_restart_and_owner_guard(tmp_path):
    path = tmp_path / "secret.db"
    url = "sqlite:///" + path.as_posix()
    key = "a" * 40
    db = ConnectionDB(url, key)
    data = asdict(DikidiCredentials("phone", "sensitive-password", "1", "7", "owner"))
    db.save(data)
    db.engine.dispose()
    assert b"sensitive-password" not in path.read_bytes()
    reopened = ConnectionDB(url, key)
    assert reopened.load() == data
    with pytest.raises(PermissionError):
        reopened.save({**data, "owner_id":"other"})
    with pytest.raises(InvalidToken):
        ConnectionDB(url, "b" * 40).load()


def test_company_parser_is_scoped_to_crm_navigation():
    html = '''<a href="/ru/owner/journal/?company=12">Салон Анны</a>
    <a href="/ru/owner/journal/?company=13">Второй салон</a>
    <a href="https://evil.test/ru/owner/?company=99">Лишний</a>
    <a href="/ru/owner/?company=abc">Не ID</a>'''
    assert parse_companies(html) == {"12":"Салон Анны", "13":"Второй салон"}
