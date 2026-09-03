from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Competitor Intel Search"
    app_env: str = "development"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "user"
    db_pass: str = "password"
    db_name: str = "competitor_intel"
    db_schema: str = "competitor"
    auth_username: str = "admin"
    auth_password: str = "change-this-password"
    auth_secret: str = "replace-with-a-long-random-secret"
    database_url: str = (
        "postgresql+psycopg://user:password@localhost:5432/competitor_intel"
        "?options=-csearch_path%3Dcompetitor"
    )

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
