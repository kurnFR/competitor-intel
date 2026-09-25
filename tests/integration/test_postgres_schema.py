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

    column_expectations = {
        "crawl_jobs": {"next_retry_at", "max_retries", "last_attempt_at", "worker_id"},
        "crawl_documents": {"raw_content_sha256", "raw_content_type", "raw_content_size_bytes", "storage_backend"},
        "entity_mapping": {"normalized_source_value", "resolution_status", "review_queue_id"},
        "promotion_observations": {
            "promotion_id",
            "extraction_model",
            "extraction_status",
            "extracted_at",
            "extraction_raw_response_hash",
            "extraction_rejected_count",
        },
        "promotions": {
            "identity_fingerprint",
            "identity_version",
            "source_identity_fingerprint",
            "supersedes_promotion_id",
        },
        "review_queue": {"candidate_entity_id", "promotion_id", "observation_id", "confidence"},
        "promotion_change_events": {
            "promotion_id",
            "previous_promotion_id",
            "observation_id",
            "document_id",
            "event_type",
            "event_fingerprint",
        },
    }
    for table, expected_columns in column_expectations.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table, schema=SCHEMA)}
        assert expected_columns.issubset(actual_columns), table


def test_migration_version_is_current(engine):
    with engine.connect() as conn:
        revision = conn.execute(
            text(f'SELECT version_num FROM "{SCHEMA}".alembic_version')
        ).scalar_one()
    assert revision
