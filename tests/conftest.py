import pytest

from app.alice import session_store
from app.alice.models import AliceRequestBody
from app.dikidi.mock_client import MockDikidiClient


def build_request(
    command: str,
    original: str | None = None,
    entities: list[dict] | None = None,
    state: dict | None = None,
    new: bool = False,
    session_id: str = "test-session",
    include_state: bool = True,
) -> AliceRequestBody:
    payload = {
        "request": {
            "command": command,
            "original_utterance": original if original is not None else command,
            "nlu": {"entities": entities or []},
        },
        "session": {"new": new, "session_id": session_id},
    }
    if include_state:
        payload["state"] = {"session": state or {}}
    return AliceRequestBody.model_validate(payload)


@pytest.fixture(autouse=True)
def _clear_session_store():
    session_store._store.clear()
    yield
    session_store._store.clear()


@pytest.fixture
def dikidi():
    return MockDikidiClient()
