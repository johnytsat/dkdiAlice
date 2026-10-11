from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "mock" — для разработки/тестов без реальной Dikidi,
    # "sdk"  — вход по телефону и паролю через пакет dikidi-api-client,
    # "http" — официальный API, когда Dikidi выдаст партнёрский токен.
    dikidi_backend: Literal["mock", "sdk", "http"] = "mock"
    public_base_url: str = ""
    alice_owner_id: str = ""
    database_url: str = ""
    credentials_encryption_key: str = ""

    # Для backend=sdk (вход как в браузере).
    dikidi_phone: str = ""
    dikidi_password: str = ""

    # Для backend=http (официальный API).
    dikidi_token: str = ""

    dikidi_company_id: str = ""
    # Пусто/0 — взять первого мастера из каталога.
    dikidi_default_staff_id: str = ""


settings = Settings()
