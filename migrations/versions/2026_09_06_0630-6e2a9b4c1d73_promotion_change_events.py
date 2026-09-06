"""Add immutable promotion change event history.

Revision ID: 6e2a9b4c1d73
Revises: 5d1f8a3c7b92
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6e2a9b4c1d73"
down_revision = "5d1f8a3c7b92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promotion_change_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("promotion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_promotion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=True),
        sa.Column("previous_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("change_impact", sa.Float(), nullable=False, server_default="0"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["promotion_id"], ["competitor_intel.promotions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_promotion_id"], ["competitor_intel.promotions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["observation_id"], ["competitor_intel.promotion_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["competitor_intel.crawl_documents.id"], ondelete="SET NULL"),
        schema="competitor_intel",
    )
    op.create_unique_constraint(
        "uq_promotion_change_event_fingerprint",
        "promotion_change_events",
        ["event_fingerprint"],
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotion_change_events_promotion_observed",
        "promotion_change_events",
        ["promotion_id", "observed_at"],
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotion_change_events_type_observed",
        "promotion_change_events",
        ["event_type", "observed_at"],
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotion_change_events_observation",
        "promotion_change_events",
        ["observation_id"],
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index("idx_promotion_change_events_observation", table_name="promotion_change_events", schema="competitor_intel")
    op.drop_index("idx_promotion_change_events_type_observed", table_name="promotion_change_events", schema="competitor_intel")
    op.drop_index("idx_promotion_change_events_promotion_observed", table_name="promotion_change_events", schema="competitor_intel")
    op.drop_constraint("uq_promotion_change_event_fingerprint", "promotion_change_events", schema="competitor_intel", type_="unique")
    op.drop_table("promotion_change_events", schema="competitor_intel")
