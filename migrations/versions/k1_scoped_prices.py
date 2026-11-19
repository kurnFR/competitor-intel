"""Effective-dated retailer and area pricing."""

from alembic import op

revision = "k1_scoped_prices"
down_revision = "j9_field_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE competitor_intel.scoped_prices (
        id uuid PRIMARY KEY, product_id uuid NOT NULL REFERENCES competitor_intel.own_products(id) ON DELETE CASCADE,
        retailer_id uuid NOT NULL REFERENCES competitor_intel.retailers(id), region text NOT NULL,
        starts date NOT NULL, ends date NOT NULL CHECK (ends >= starts),
        regular_price numeric(14,2) NOT NULL CHECK (regular_price>0),
        promo_price numeric(14,2) CHECK (promo_price>0 AND promo_price<=regular_price),
        recorded_by uuid NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp())""")
    op.execute("CREATE INDEX scoped_price_period ON competitor_intel.scoped_prices(retailer_id,region,product_id,starts,ends)")


def downgrade():
    op.execute("DROP TABLE competitor_intel.scoped_prices")
