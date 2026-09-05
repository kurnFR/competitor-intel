"""Add raw object provenance to crawl documents.

Revision ID: 91c4e7a2b5d8
Revises: f6a91c3d8e52
"""

from alembic import op
import sqlalchemy as sa

revision = "91c4e7a2b5d8"
down_revision = "f6a91c3d8e52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_documents", sa.Column("raw_content_sha256", sa.String(64), nullable=True), schema="competitor_intel")
    op.add_column("crawl_documents", sa.Column("raw_content_type", sa.String(100), nullable=True), schema="competitor_intel")
    op.add_column("crawl_documents", sa.Column("raw_content_size_bytes", sa.BigInteger(), nullable=True), schema="competitor_intel")
    op.add_column("crawl_documents", sa.Column("storage_backend", sa.String(30), nullable=True), schema="competitor_intel")
    op.create_index("idx_crawl_documents_raw_sha256", "crawl_documents", ["raw_content_sha256"], schema="competitor_intel")


def downgrade() -> None:
    op.drop_index("idx_crawl_documents_raw_sha256", table_name="crawl_documents", schema="competitor_intel")
    op.drop_column("crawl_documents", "storage_backend", schema="competitor_intel")
    op.drop_column("crawl_documents", "raw_content_size_bytes", schema="competitor_intel")
    op.drop_column("crawl_documents", "raw_content_type", schema="competitor_intel")
    op.drop_column("crawl_documents", "raw_content_sha256", schema="competitor_intel")
