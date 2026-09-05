"""Add durable retry scheduling state to crawl jobs.

Revision ID: f6a91c3d8e52
Revises: e5d72a1c9b40
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a91c3d8e52"
down_revision = "e5d72a1c9b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crawl_jobs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        schema="competitor_intel",
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "crawl_jobs",
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_crawl_jobs_retry_queue",
        "crawl_jobs",
        ["status", "next_retry_at"],
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_crawl_jobs_retry_queue",
        table_name="crawl_jobs",
        schema="competitor_intel",
    )
    op.drop_column("crawl_jobs", "worker_id", schema="competitor_intel")
    op.drop_column("crawl_jobs", "last_attempt_at", schema="competitor_intel")
    op.drop_column("crawl_jobs", "max_retries", schema="competitor_intel")
    op.drop_column("crawl_jobs", "next_retry_at", schema="competitor_intel")
