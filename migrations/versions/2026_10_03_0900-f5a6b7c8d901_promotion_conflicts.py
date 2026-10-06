"""Flag promotions with an unresolved multi-source conflict.

Revision ID: f5a6b7c8d901
Revises: e4f5a6b7c801
"""
from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d901"
down_revision = "e4f5a6b7c801"
branch_labels = None
depends_on = None

S = "competitor_intel"


def upgrade() -> None:
    op.add_column("promotions", sa.Column("has_open_conflict", sa.Boolean(), nullable=False, server_default=sa.false()), schema=S)


def downgrade() -> None:
    op.drop_column("promotions", "has_open_conflict", schema=S)
