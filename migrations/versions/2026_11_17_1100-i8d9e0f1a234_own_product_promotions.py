"""Add promotional pricing and mechanic fields to own_products.

Revision ID: i8d9e0f1a234
Revises: h7c8d9e0f123
"""
from alembic import op
import sqlalchemy as sa

revision = "i8d9e0f1a234"
down_revision = "h7c8d9e0f123"
branch_labels = None
depends_on = None

SCHEMA = "competitor_intel"


def upgrade() -> None:
    op.add_column("own_products", sa.Column("promo_price", sa.Float(), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("promo_type", sa.String(50), nullable=False, server_default="REGULAR"), schema=SCHEMA)
    op.add_column("own_products", sa.Column("promo_start_date", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("promo_end_date", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("promo_mechanic", sa.String(100), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("buy_quantity", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("free_quantity", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("buy_x", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("own_products", sa.Column("get_y", sa.Integer(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("own_products", "get_y", schema=SCHEMA)
    op.drop_column("own_products", "buy_x", schema=SCHEMA)
    op.drop_column("own_products", "free_quantity", schema=SCHEMA)
    op.drop_column("own_products", "buy_quantity", schema=SCHEMA)
    op.drop_column("own_products", "promo_mechanic", schema=SCHEMA)
    op.drop_column("own_products", "promo_end_date", schema=SCHEMA)
    op.drop_column("own_products", "promo_start_date", schema=SCHEMA)
    op.drop_column("own_products", "promo_type", schema=SCHEMA)
    op.drop_column("own_products", "promo_price", schema=SCHEMA)
