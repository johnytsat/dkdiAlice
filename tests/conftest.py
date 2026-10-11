import pytest

from app.alice.models import AliceRequestBody
from app.dikidi.mock_client import MockDikidiClient


def build_request(
    command: str,
    original: str | None = None,
    entities: list[dict] | None = None,
    state: dict | None = None,
    new: bool = False,
) -> AliceRequestBody:
    return AliceRequestBody.model_validate(
        {
            "request": {
                "command": command,
                "original_utterance": original if original is not None else command,
                "nlu": {"entities": entities or []},
            },
            "session": {"new": new, "session_id": "test-session"},
            "state": {"session": state or {}},
        }
    )


@pytest.fixture
def dikidi():
    return MockDikidiClient()
