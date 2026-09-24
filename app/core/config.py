import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Competitor Promotion Intelligence Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/competitor_intel"
    DATABASE_URL_ADMIN: Optional[str] = None
    DATABASE_SCHEMA: str = "competitor_intel"

    REDIS_URL: str = "redis://localhost:6379/0"

    LLM_BASE_URL: str = "http://localhost:20128/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "auto/best-fast"

    CRAWL_INTERVAL_MINUTES: int = 30
    EXPIRATION_CHECK_MINUTES: int = 15
    MAX_CONCURRENT_CRAWLS: int = 5
    RECENCY_MONTHS: int = 3

    # Administrative API controls. Leave ADMIN_API_TOKEN unset in development
    # only if administrative endpoints are not exposed outside a trusted network.
    ADMIN_API_TOKEN: Optional[str] = None
    CORS_ALLOWED_ORIGINS: str = ""


settings = Settings()
