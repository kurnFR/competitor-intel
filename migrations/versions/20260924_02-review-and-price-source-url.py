"""Add review audit and exact regional price evidence URL.

Revision ID: 20260924_02
Revises: 20260924_01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260924_02"
down_revision = "20260924_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promotion_price_observations",
        sa.Column("source_url", sa.Text(), nullable=True),
        schema="competitor_intel",
    )
    op.create_table(
        "promotion_review_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("promotion_id", sa.UUID(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["promotion_id"],
            ["competitor_intel.promotions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotion_review_decisions_promotion",
        "promotion_review_decisions",
        ["promotion_id"],
        unique=False,
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotion_review_decisions_reviewed_at",
        "promotion_review_decisions",
        ["reviewed_at"],
        unique=False,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_promotion_review_decisions_reviewed_at",
        table_name="promotion_review_decisions",
        schema="competitor_intel",
    )
    op.drop_index(
        "idx_promotion_review_decisions_promotion",
        table_name="promotion_review_decisions",
        schema="competitor_intel",
    )
    op.drop_table("promotion_review_decisions", schema="competitor_intel")
    op.drop_column(
        "promotion_price_observations",
        "source_url",
        schema="competitor_intel",
    )
