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

    # LLM (9router)
    LLM_BASE_URL: str = "http://localhost:20128/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "auto/best-fast"

    # Security / login
    # Cookie "Secure" flag. Unset = automatic (on when APP_ENV=production). Serve over HTTPS in production.
    SESSION_COOKIE_SECURE: Optional[bool] = None
    SESSION_ABSOLUTE_HOURS: int = 12
    SESSION_IDLE_MINUTES: int = 120
    LOGIN_MAX_FAILURES: int = 5          # per account before a temporary lock
    LOGIN_LOCK_MINUTES: int = 15
    LOGIN_IP_MAX_FAILURES: int = 20      # per client IP within LOGIN_IP_WINDOW_MINUTES
    LOGIN_IP_WINDOW_MINUTES: int = 10
    PASSWORD_MIN_LENGTH: int = 12
    # Two-factor authentication. SECRET_KEY encrypts the stored authenticator secrets and signs
    # login challenges; without it 2FA is unavailable. Generate once and keep it safe (changing it
    # invalidates enrolled authenticators):  python -c "import secrets; print(secrets.token_urlsafe(48))"
    SECRET_KEY: str = ""
    MFA_REQUIRED_FOR_ADMINS: bool = False
    MFA_CHALLENGE_SECONDS: int = 300
    # Only enable behind a reverse proxy you control; trusts X-Forwarded-For for the client IP.
    TRUST_PROXY: bool = False

    # Weekly e-mail digest (optional). Needs SMTP_HOST and DIGEST_RECIPIENTS.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    DIGEST_RECIPIENTS: str = ""          # comma-separated
    # Optional chat webhook (Slack, Google Chat, Mattermost: JSON {"text": ...}). Must be https.
    DIGEST_WEBHOOK_URL: str = ""
    DIGEST_DAY_OF_WEEK: str = "mon"
    DIGEST_HOUR: int = 8

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
    def session_cookie_secure(self) -> bool:
        if self.SESSION_COOKIE_SECURE is not None:
            return self.SESSION_COOKIE_SECURE
        return self.APP_ENV.lower() == "production"

    @property
    def digest_recipient_list(self) -> list[str]:
        return [r.strip() for r in self.DIGEST_RECIPIENTS.split(",") if r.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
