from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "sqlite:///./cove2e.db"

    # Sarvam
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    SARVAM_CHAT_MODEL: str = "sarvam-105b"
    SARVAM_STT_MODEL: str = "saaras:v3"
    SARVAM_TRANSLATE_MODEL: str = "sarvam-translate:v1"
    SARVAM_TTS_MODEL: str = "bulbul:v2"
    SARVAM_TIMEOUT_SECONDS: float = 40.0

    # Cognee
    COGNEE_API_KEY: str = ""
    COGNEE_ENABLED: bool = False

    # n8n
    N8N_BASE_URL: str = "http://localhost:5678"
    N8N_WEBHOOK_SECRET: str = "change-me-n8n-secret"
    N8N_TIMEOUT_SECONDS: float = 30.0
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"

    # Auth
    JWT_SECRET: str = "change-me-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720

    # App
    APP_ENV: str = "development"
    DEMO_MODE: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 10

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sarvam_configured(self) -> bool:
        return bool(self.SARVAM_API_KEY)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
