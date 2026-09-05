"""Add extraction provenance to promotion observations.

Revision ID: e5d72a1c9b40
Revises: c4a81e6f2b73
"""

from alembic import op
import sqlalchemy as sa


revision = "e5d72a1c9b40"
down_revision = "c4a81e6f2b73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promotion_observations",
        sa.Column("extraction_model", sa.String(length=255), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "promotion_observations",
        sa.Column("extraction_status", sa.String(length=50), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "promotion_observations",
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "promotion_observations",
        sa.Column("extraction_raw_response_hash", sa.String(length=64), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "promotion_observations",
        sa.Column("extraction_rejected_count", sa.Integer(), nullable=True),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotion_observations_extraction_status",
        "promotion_observations",
        ["extraction_status"],
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_promotion_observations_extraction_status",
        table_name="promotion_observations",
        schema="competitor_intel",
    )
    op.drop_column("promotion_observations", "extraction_rejected_count", schema="competitor_intel")
    op.drop_column("promotion_observations", "extraction_raw_response_hash", schema="competitor_intel")
    op.drop_column("promotion_observations", "extracted_at", schema="competitor_intel")
    op.drop_column("promotion_observations", "extraction_status", schema="competitor_intel")
    op.drop_column("promotion_observations", "extraction_model", schema="competitor_intel")
