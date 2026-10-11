from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    dikidi_token: str = ""
    dikidi_company_id: str = ""
    dikidi_default_staff_id: int = 0

    # "mock" для разработки/тестов без реального Dikidi, "http" для продакшена
    dikidi_backend: str = "mock"


settings = Settings()
