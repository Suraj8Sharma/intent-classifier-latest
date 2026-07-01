from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

CLASSIFY_TIMEOUT_MS = 200
GENERATE_TIMEOUT_MS = 800


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    local_model_endpoint: str
    supabase_url: str | None = None
    supabase_key: str | None = None


settings = Settings()
