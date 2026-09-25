"""reconcile competitor_intel schema drift with current application contract

Revision ID: a8c4e1f9d2b7
Revises: 7f3a1c9e5b20

The 2026-09-24 PostgreSQL schema snapshot showed a database that is missing
columns introduced by already-committed migrations and the
promotion_change_events table. This reconciliation migration is intentionally
idempotent so it is safe on databases that already contain the objects.

It does not add a promotion fingerprint UNIQUE constraint; collisions must be
audited before canonical identity is enforced.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c4e1f9d2b7"
down_revision: Union[str, None] = "7f3a1c9e5b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "competitor_intel"


def _add_column(table: str, column_sql: str) -> None:
    op.execute(
        f'ALTER TABLE "{SCHEMA}"."{table}" '
        f'ADD COLUMN IF NOT EXISTS {column_sql}'
    )


def _add_fk(constraint_name: str, table: str, column: str, ref_table: str, ref_column: str, ondelete: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
                  AND conrelid = '{SCHEMA}.{table}'::regclass
            ) THEN
                ALTER TABLE "{SCHEMA}"."{table}"
                ADD CONSTRAINT "{constraint_name}"
                FOREIGN KEY ("{column}")
                REFERENCES "{SCHEMA}"."{ref_table}" ("{ref_column}")
                ON DELETE {ondelete};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # Crawl job retry/resume state.
    _add_column("crawl_jobs", 'next_retry_at TIMESTAMPTZ')
    _add_column("crawl_jobs", 'max_retries INTEGER NOT NULL DEFAULT 3')
    _add_column("crawl_jobs", 'last_attempt_at TIMESTAMPTZ')
    _add_column("crawl_jobs", 'worker_id VARCHAR(100)')

    # Raw document/object provenance.
    _add_column("crawl_documents", 'raw_content_sha256 VARCHAR(64)')
    _add_column("crawl_documents", 'raw_content_type VARCHAR(100)')
    _add_column("crawl_documents", 'raw_content_size_bytes BIGINT')
    _add_column("crawl_documents", 'storage_backend VARCHAR(30)')

    # Conservative entity resolution audit state.
    _add_column("entity_mapping", 'normalized_source_value VARCHAR(255)')
    _add_column("entity_mapping", 'resolution_status VARCHAR(30) NOT NULL DEFAULT \'APPROVED\'')
    _add_column("entity_mapping", 'review_queue_id UUID')
    _add_fk(
        "fk_entity_mapping_review_queue",
        "entity_mapping",
        "review_queue_id",
        "review_queue",
        "id",
        "SET NULL",
    )

    # Observation-to-canonical-promotion linkage and extraction provenance.
    _add_column("promotion_observations", 'promotion_id UUID')
    _add_column("promotion_observations", 'extraction_model VARCHAR(255)')
    _add_column("promotion_observations", 'extraction_status VARCHAR(50)')
    _add_column("promotion_observations", 'extracted_at TIMESTAMPTZ')
    _add_column("promotion_observations", 'extraction_raw_response_hash VARCHAR(64)')
    _add_column("promotion_observations", 'extraction_rejected_count INTEGER')
    _add_fk(
        "fk_promotion_observations_promotion_id",
        "promotion_observations",
        "promotion_id",
        "promotions",
        "id",
        "SET NULL",
    )

    # Canonical promotion identity and lineage.
    _add_column("promotions", 'identity_fingerprint VARCHAR(64)')
    _add_column("promotions", 'identity_version VARCHAR(20) NOT NULL DEFAULT \'v1\'')
    _add_column("promotions", 'source_identity_fingerprint VARCHAR(64)')
    _add_column("promotions", 'supersedes_promotion_id UUID')
    _add_fk(
        "fk_promotions_supersedes_promotion",
        "promotions",
        "supersedes_promotion_id",
        "promotions",
        "id",
        "SET NULL",
    )

    # Review queue context.
    _add_column("review_queue", 'candidate_entity_id UUID')
    _add_column("review_queue", 'promotion_id UUID')
    _add_column("review_queue", 'observation_id UUID')
    _add_column("review_queue", 'confidence DOUBLE PRECISION')

    # Indexes expected by the current ORM and existing migrations.
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_crawl_jobs_retry_queue" '
        f'ON "{SCHEMA}"."crawl_jobs" ("status", "next_retry_at")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_crawl_documents_raw_sha256" '
        f'ON "{SCHEMA}"."crawl_documents" ("raw_content_sha256")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_entity_mapping_type_normalized" '
        f'ON "{SCHEMA}"."entity_mapping" ("entity_type", "normalized_source_value")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotion_observations_promotion_id" '
        f'ON "{SCHEMA}"."promotion_observations" ("promotion_id")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotion_observations_extraction_status" '
        f'ON "{SCHEMA}"."promotion_observations" ("extraction_status")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotions_identity_fingerprint" '
        f'ON "{SCHEMA}"."promotions" ("identity_fingerprint")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotions_source_identity_fingerprint" '
        f'ON "{SCHEMA}"."promotions" ("source_identity_fingerprint")'
    )

    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_review_queue_promotion" '
        f'ON "{SCHEMA}"."review_queue" ("promotion_id")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_review_queue_observation" '
        f'ON "{SCHEMA}"."review_queue" ("observation_id")'
    )

    # Immutable promotion-change history was already part of the committed
    # migration chain, but the captured database does not contain the table.
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{SCHEMA}"."promotion_change_events" (
            id UUID PRIMARY KEY,
            promotion_id UUID NOT NULL
                REFERENCES "{SCHEMA}"."promotions"(id) ON DELETE CASCADE,
            previous_promotion_id UUID
                REFERENCES "{SCHEMA}"."promotions"(id) ON DELETE SET NULL,
            observation_id UUID
                REFERENCES "{SCHEMA}"."promotion_observations"(id) ON DELETE SET NULL,
            document_id UUID
                REFERENCES "{SCHEMA}"."crawl_documents"(id) ON DELETE SET NULL,
            event_type VARCHAR(50) NOT NULL,
            field_name VARCHAR(100),
            previous_value JSONB,
            new_value JSONB,
            change_impact DOUBLE PRECISION NOT NULL DEFAULT 0,
            observed_at TIMESTAMPTZ NOT NULL,
            event_fingerprint VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_promotion_change_event_fingerprint" '
        f'ON "{SCHEMA}"."promotion_change_events" ("event_fingerprint")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotion_change_events_promotion_observed" '
        f'ON "{SCHEMA}"."promotion_change_events" ("promotion_id", "observed_at")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotion_change_events_type_observed" '
        f'ON "{SCHEMA}"."promotion_change_events" ("event_type", "observed_at")'
    )
    op.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_promotion_change_events_observation" '
        f'ON "{SCHEMA}"."promotion_change_events" ("observation_id")'
    )


def downgrade() -> None:
    # This is a live-schema reconciliation migration. Objects may have existed
    # before this revision, so automatically dropping them would be unsafe.
    pass
