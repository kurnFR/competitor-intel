"""Link promotions to their source where the link is still missing (safe to run on any database, any number of times).

Revision e4f5a6b7c801 was later edited to also backfill promotions.source_id from stored evidence. A database that had
already run the earlier version of that revision never received this step, so it is repeated here as its own revision.
Only promotions whose source_id is still NULL are touched.

Revision ID: h7c8d9e0f123
Revises: g6b7c8d9e012
"""
from alembic import op

revision = "h7c8d9e0f123"
down_revision = "g6b7c8d9e012"
branch_labels = None
depends_on = None

S = "competitor_intel"


def upgrade() -> None:
    op.execute(f"""
        UPDATE {S}.promotions p SET source_id = latest.source_id
        FROM (
            SELECT DISTINCT ON (o.promotion_id) o.promotion_id, d.source_id
            FROM {S}.promotion_observations o JOIN {S}.crawl_documents d ON d.id = o.document_id
            WHERE o.promotion_id IS NOT NULL AND d.source_id IS NOT NULL
            ORDER BY o.promotion_id, o.observed_at DESC
        ) latest WHERE latest.promotion_id = p.id AND p.source_id IS NULL;

        UPDATE {S}.promotions p SET source_id = latest.source_id
        FROM (
            SELECT DISTINCT ON (e.promotion_id) e.promotion_id, d.source_id
            FROM {S}.promotion_evidence e JOIN {S}.crawl_documents d ON d.id = e.document_id
            WHERE e.promotion_id IS NOT NULL AND d.source_id IS NOT NULL
            ORDER BY e.promotion_id, e.captured_at DESC
        ) latest WHERE latest.promotion_id = p.id AND p.source_id IS NULL;
    """)


def downgrade() -> None:
    pass        # a data backfill; nothing to undo
