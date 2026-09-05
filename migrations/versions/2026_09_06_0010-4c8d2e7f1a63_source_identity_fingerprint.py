"""Add stable source-observed promotion identity fingerprint.

Revision ID: 4c8d2e7f1a63
Revises: b7e41c2d8f90
"""

from alembic import op
import sqlalchemy as sa


revision = "4c8d2e7f1a63"
down_revision = "b7e41c2d8f90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("source_identity_fingerprint", sa.String(length=64), nullable=True),
        schema="competitor_intel",
    )
    op.create_index(
        "idx_promotions_source_identity_fingerprint",
        "promotions",
        ["source_identity_fingerprint"],
        unique=False,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_promotions_source_identity_fingerprint",
        table_name="promotions",
        schema="competitor_intel",
    )
    op.drop_column(
        "promotions",
        "source_identity_fingerprint",
        schema="competitor_intel",
    )
