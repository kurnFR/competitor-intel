"""Add promotion supersession lineage.

Revision ID: 5d1f8a3c7b92
Revises: 4c8d2e7f1a63
"""
from alembic import op
import sqlalchemy as sa

revision = "5d1f8a3c7b92"
down_revision = "4c8d2e7f1a63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "promotions",
        sa.Column("supersedes_promotion_id", sa.UUID(), nullable=True),
        schema="competitor_intel",
    )
    op.create_foreign_key(
        "fk_promotions_supersedes_promotion",
        "promotions",
        "promotions",
        ["supersedes_promotion_id"],
        ["id"],
        source_schema="competitor_intel",
        referent_schema="competitor_intel",
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_promotions_lineage_parent",
        "promotions",
        ["supersedes_promotion_id"],
        unique=False,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index("idx_promotions_lineage_parent", table_name="promotions", schema="competitor_intel")
    op.drop_constraint(
        "fk_promotions_supersedes_promotion",
        "promotions",
        schema="competitor_intel",
        type_="foreignkey",
    )
    op.drop_column("promotions", "supersedes_promotion_id", schema="competitor_intel")
