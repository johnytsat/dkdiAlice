from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NluEntity(BaseModel):
    type: str
    value: dict[str, Any] | int | str | None = None
    tokens: dict[str, Any] | None = None


class Nlu(BaseModel):
    tokens: list[str] = Field(default_factory=list)
    entities: list[NluEntity] = Field(default_factory=list)


class AliceRequest(BaseModel):
    command: str = ""
    original_utterance: str = ""
    type: str = "SimpleUtterance"
    nlu: Nlu = Field(default_factory=Nlu)


class AliceSession(BaseModel):
    new: bool = False
    message_id: int = 0
    session_id: str = ""
    skill_id: str = ""
    user_id: str | None = None


class AliceState(BaseModel):
    session: dict[str, Any] = Field(default_factory=dict)


class AliceRequestBody(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    request: AliceRequest = Field(default_factory=AliceRequest)
    session: AliceSession = Field(default_factory=AliceSession)
    state: AliceState = Field(default_factory=AliceState)
    version: str = "1.0"


class AliceResponsePayload(BaseModel):
    text: str
    tts: str | None = None
    end_session: bool = False


class AliceResponseBody(BaseModel):
    response: AliceResponsePayload
    session_state: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0"
