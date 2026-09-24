"""Add explicit source adapter key.

Revision ID: 20260924_03
Revises: 20260924_02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260924_03"
down_revision = "20260924_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_registry",
        sa.Column("adapter_key", sa.String(length=50), nullable=True),
        schema="competitor_intel",
    )
    op.create_index(
        "ix_competitor_intel_source_registry_adapter_key",
        "source_registry",
        ["adapter_key"],
        unique=False,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_competitor_intel_source_registry_adapter_key",
        table_name="source_registry",
        schema="competitor_intel",
    )
    op.drop_column("source_registry", "adapter_key", schema="competitor_intel")
