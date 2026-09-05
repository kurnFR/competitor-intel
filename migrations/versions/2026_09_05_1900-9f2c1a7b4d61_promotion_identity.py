"""add promotion identity and observation linkage

Revision ID: 9f2c1a7b4d61
Revises: d7bd4ee90139
Create Date: 2026-09-05 19:00:00+07:00

This migration intentionally does not add a UNIQUE constraint to the identity
fingerprint. Existing data must be audited for collisions before uniqueness is
enforced.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f2c1a7b4d61"
down_revision: Union[str, None] = "d7bd4ee90139"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=True),
        schema="competitor_intel",
    )
    op.add_column(
        "promotions",
        sa.Column(
            "identity_version",
            sa.String(length=20),
            nullable=False,
            server_default="v1",
        ),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotions_identity_fingerprint",
        "promotions",
        ["identity_fingerprint"],
        unique=False,
        schema="competitor_intel",
    )

    op.add_column(
        "promotion_observations",
        sa.Column("promotion_id", sa.UUID(), nullable=True),
        schema="competitor_intel",
    )
    op.create_foreign_key(
        "fk_promotion_observations_promotion_id",
        "promotion_observations",
        "promotions",
        ["promotion_id"],
        ["id"],
        source_schema="competitor_intel",
        referent_schema="competitor_intel",
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_promotion_observations_promotion_id",
        "promotion_observations",
        ["promotion_id"],
        unique=False,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_promotion_observations_promotion_id",
        table_name="promotion_observations",
        schema="competitor_intel",
    )
    op.drop_constraint(
        "fk_promotion_observations_promotion_id",
        "promotion_observations",
        schema="competitor_intel",
        type_="foreignkey",
    )
    op.drop_column(
        "promotion_observations",
        "promotion_id",
        schema="competitor_intel",
    )

    op.drop_index(
        "idx_promotions_identity_fingerprint",
        table_name="promotions",
        schema="competitor_intel",
    )
    op.drop_column("promotions", "identity_version", schema="competitor_intel")
    op.drop_column("promotions", "identity_fingerprint", schema="competitor_intel")
