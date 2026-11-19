"""Reviewed competitor matches for own SKUs."""

from alembic import op

revision = "m3_reviewed_matches"
down_revision = "l2_field_revisions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE competitor_intel.product_matches (
        own_id uuid NOT NULL REFERENCES competitor_intel.own_products(id) ON DELETE CASCADE,
        offer_key text NOT NULL, product_name text NOT NULL, accepted boolean NOT NULL,
        reviewed_by uuid NOT NULL, reviewed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(own_id,offer_key))""")


def downgrade():
    op.execute("DROP TABLE competitor_intel.product_matches")
