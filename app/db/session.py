from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Application engine (uses competitor_intel_app)
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    connect_args={"options": f"-csearch_path={settings.DATABASE_SCHEMA},public"}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
