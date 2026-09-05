"""strengthen entity resolution audit persistence

Revision ID: b7e41c2d8f90
Revises: 9f2c1a7b4d61

Adds normalized alias values and explicit review linkage so conservative
resolution decisions can be persisted and audited without auto-creating
canonical entities.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e41c2d8f90"
down_revision: Union[str, None] = "9f2c1a7b4d61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_mapping",
        sa.Column("normalized_source_value", sa.String(length=255), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "entity_mapping",
        sa.Column("resolution_status", sa.String(length=30), nullable=False, server_default="APPROVED"),
        schema="competitor_intel",
    )
    op.add_column(
        "entity_mapping",
        sa.Column("review_queue_id", sa.UUID(), nullable=True),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_entity_mapping_type_normalized",
        "entity_mapping",
        ["entity_type", "normalized_source_value"],
        unique=False,
        schema="competitor_intel",
    )
    op.create_foreign_key(
        "fk_entity_mapping_review_queue",
        "entity_mapping",
        "review_queue",
        ["review_queue_id"],
        ["id"],
        source_schema="competitor_intel",
        referent_schema="competitor_intel",
        ondelete="SET NULL",
    )

    op.add_column(
        "review_queue",
        sa.Column("promotion_id", sa.UUID(), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "review_queue",
        sa.Column("observation_id", sa.UUID(), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "review_queue",
        sa.Column("candidate_entity_id", sa.UUID(), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "review_queue",
        sa.Column("confidence", sa.Float(), nullable=True),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_review_queue_promotion",
        "review_queue",
        ["promotion_id"],
        unique=False,
        schema="competitor_intel",
    )
    op.create_index(
        "idx_review_queue_observation",
        "review_queue",
        ["observation_id"],
        unique=False,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index("idx_review_queue_observation", table_name="review_queue", schema="competitor_intel")
    op.drop_index("idx_review_queue_promotion", table_name="review_queue", schema="competitor_intel")
    op.drop_column("review_queue", "confidence", schema="competitor_intel")
    op.drop_column("review_queue", "candidate_entity_id", schema="competitor_intel")
    op.drop_column("review_queue", "observation_id", schema="competitor_intel")
    op.drop_column("review_queue", "promotion_id", schema="competitor_intel")

    op.drop_constraint("fk_entity_mapping_review_queue", "entity_mapping", schema="competitor_intel", type_="foreignkey")
    op.drop_index("idx_entity_mapping_type_normalized", table_name="entity_mapping", schema="competitor_intel")
    op.drop_column("entity_mapping", "review_queue_id", schema="competitor_intel")
    op.drop_column("entity_mapping", "resolution_status", schema="competitor_intel")
    op.drop_column("entity_mapping", "normalized_source_value", schema="competitor_intel")
