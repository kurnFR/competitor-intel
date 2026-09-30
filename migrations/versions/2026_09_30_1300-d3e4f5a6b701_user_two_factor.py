"""Add two-factor (TOTP) columns to users.

Revision ID: d3e4f5a6b701
Revises: c2d3e4f5a601
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d3e4f5a6b701"
down_revision = "c2d3e4f5a601"
branch_labels = None
depends_on = None

SCHEMA = "competitor_intel"


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_enc", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True), schema=SCHEMA)
    op.add_column("users", sa.Column("recovery_hashes", postgresql.JSONB(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for col in ("recovery_hashes", "totp_last_step", "totp_enabled", "totp_secret_enc"):
        op.drop_column("users", col, schema=SCHEMA)
