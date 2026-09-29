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
    DEBUG: bool = False
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
    LLM_MODEL: str = "auto/best-fast"

    # Security
    # Required for privileged endpoints (POST /api/v1/pipeline/run). If empty the
    # endpoint is disabled. Generate one with:
    #   python -c "import secrets; print(secrets.token_urlsafe(32))"
    ADMIN_API_KEY: str = ""
    # Comma-separated list of browser origins allowed to call the API cross-origin.
    # The bundled dashboard is same-origin and needs no entry.
    CORS_ORIGINS: str = ""

    # Crawler etiquette
    CRAWLER_USER_AGENT: str = "CompetitorIntelBot/1.0"
    CRAWLER_RESPECT_ROBOTS: bool = True

    # Engine Tuning
    CRAWL_INTERVAL_MINUTES: int = 1440
    EXPIRATION_CHECK_MINUTES: int = 15
    MAX_CONCURRENT_CRAWLS: int = 5
    RECENCY_MONTHS: int = 3
    # Promotions whose dates are not stated on the page stay visible this many days
    # after they were last seen on a source.
    UNDATED_PROMO_MAX_AGE_DAYS: int = 14
    # Extraction limits per crawled document.
    MAX_CARDS_PER_DOCUMENT: int = 300
    CARDS_PER_LLM_BATCH: int = 6

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
