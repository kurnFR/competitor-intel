import os

import pytest
from sqlalchemy import create_engine, inspect, text


DATABASE_URL = os.getenv("DATABASE_URL")
SCHEMA = os.getenv("DATABASE_SCHEMA", "competitor_intel")


@pytest.fixture(scope="module")
def engine():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield engine
    engine.dispose()


def test_schema_and_required_extensions(engine):
    with engine.connect() as conn:
        schema_exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
            {"schema": SCHEMA},
        ).scalar_one()
        assert schema_exists

        extensions = {
            row[0]
            for row in conn.execute(
                text("SELECT extname FROM pg_extension")
            ).all()
        }
        assert "pg_trgm" in extensions
        assert "uuid-ossp" in extensions


def test_core_tables_and_foreign_keys(engine):
    inspector = inspect(engine)
    expected = {
        "competitors",
        "brands",
        "products",
        "retailers",
        "source_registry",
        "crawl_jobs",
        "crawl_documents",
        "promotion_observations",
        "promotions",
        "promotion_evidence",
        "entity_mapping",
        "review_queue",
        "promotion_change_events",
    }

    tables = set(inspector.get_table_names(schema=SCHEMA))
    assert expected.issubset(tables)

    promotion_fks = inspector.get_foreign_keys("promotions", schema=SCHEMA)
    targets = {
        fk["referred_table"]
        for fk in promotion_fks
        if fk.get("referred_schema") == SCHEMA
    }
    assert {"competitors", "brands", "products", "retailers"}.issubset(targets)


def test_migration_version_is_current(engine):
    with engine.connect() as conn:
        revision = conn.execute(
            text(f'SELECT version_num FROM "{SCHEMA}".alembic_version')
        ).scalar_one()
    assert revision
