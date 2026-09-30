"""Add own_products for price comparison against competitor promotions.

Revision ID: c2d3e4f5a601
Revises: b1c2d3e4f501
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c2d3e4f5a601"
down_revision = "b1c2d3e4f501"
branch_labels = None
depends_on = None

SCHEMA = "competitor_intel"


def upgrade() -> None:
    op.create_table(
        "own_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(120), nullable=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="BISCUIT"),
        sa.Column("pack_size", sa.String(50), nullable=True),
        sa.Column("pack_grams", sa.Float(), nullable=True),
        sa.Column("regular_price", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("regular_price > 0", name="ck_own_products_price_positive"),
        schema=SCHEMA,
    )
    op.create_index("idx_own_products_category", "own_products", ["category"], schema=SCHEMA)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'competitor_intel_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.own_products TO competitor_intel_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("own_products", schema=SCHEMA)
