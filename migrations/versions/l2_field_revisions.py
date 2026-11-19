"""Link corrected field observations to their earlier evidence."""
from alembic import op

revision = "l2_field_revisions"
down_revision = "k1_scoped_prices"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE competitor_intel.field_submissions
        ADD COLUMN previous_id uuid UNIQUE REFERENCES competitor_intel.field_submissions(id),
        ADD COLUMN review_note text""")


def downgrade():
    op.execute("ALTER TABLE competitor_intel.field_submissions DROP COLUMN previous_id,DROP COLUMN review_note")
