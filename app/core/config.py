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

    # Database
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/competitor_intel"
    DATABASE_URL_ADMIN: Optional[str] = None
    DATABASE_SCHEMA: str = "competitor_intel"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM (9router)
    LLM_BASE_URL: str = "http://localhost:20128/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "hermes-auto-fallback"

    # Engine Tuning
    CRAWL_INTERVAL_MINUTES: int = 30
    EXPIRATION_CHECK_MINUTES: int = 15
    MAX_CONCURRENT_CRAWLS: int = 5
    RECENCY_MONTHS: int = 3


settings = Settings()
