"""PRD alignment: honest geography, last_verified_at, promotion source link, source approval + adapters, scan history.

Revision ID: e4f5a6b7c801
Revises: d3e4f5a6b701
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e4f5a6b7c801"
down_revision = "d3e4f5a6b701"
branch_labels = None
depends_on = None

S = "competitor_intel"


def upgrade() -> None:
    # ---- promotions: geography was always the fabricated default "Indonesia" (the extractor never
    # produced a value), which wrongly presents every promotion as nationwide. Unknown stays unknown.
    op.alter_column("promotions", "geography", schema=S, type_=sa.String(255), nullable=True)
    op.execute(f"UPDATE {S}.promotions SET geography = NULL WHERE geography = 'Indonesia'")
    op.add_column("promotions", sa.Column("geography_region", sa.String(30), nullable=False, server_default="UNKNOWN"), schema=S)

    op.add_column("promotions", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True), schema=S)
    op.execute(f"UPDATE {S}.promotions SET last_verified_at = last_seen_at")
    op.alter_column("promotions", "last_verified_at", schema=S, nullable=False, server_default=sa.func.now())

    op.add_column("promotions", sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True), schema=S)
    op.create_foreign_key("fk_promotions_source", "promotions", "source_registry", ["source_id"], ["id"],
                          source_schema=S, referent_schema=S, ondelete="SET NULL")
    op.execute(f"""
        UPDATE {S}.promotions p SET source_id = latest.source_id
        FROM (
            SELECT DISTINCT ON (o.promotion_id) o.promotion_id, d.source_id
            FROM {S}.promotion_observations o JOIN {S}.crawl_documents d ON d.id = o.document_id
            WHERE o.promotion_id IS NOT NULL
            ORDER BY o.promotion_id, o.observed_at DESC
        ) latest WHERE latest.promotion_id = p.id;

        UPDATE {S}.promotions p SET source_id = latest.source_id
        FROM (
            SELECT DISTINCT ON (e.promotion_id) e.promotion_id, d.source_id
            FROM {S}.promotion_evidence e JOIN {S}.crawl_documents d ON d.id = e.document_id
            WHERE e.promotion_id IS NOT NULL AND d.source_id IS NOT NULL
            ORDER BY e.promotion_id, e.captured_at DESC
        ) latest WHERE latest.promotion_id = p.id AND p.source_id IS NULL;
    """)
    op.create_index("ix_promotions_source_id", "promotions", ["source_id"], schema=S)
    op.create_index("idx_promotions_last_verified", "promotions", ["last_verified_at"], schema=S)
    op.create_index("idx_promotions_geo_region", "promotions", ["geography_region"], schema=S)

    # ---- source registry: explicit approval + adapter (PRD 6: no unapproved/unsupported source is crawled)
    op.add_column("source_registry", sa.Column("approval_status", sa.String(20), nullable=False, server_default="APPROVED"), schema=S)
    op.add_column("source_registry", sa.Column("adapter_key", sa.String(40), nullable=True), schema=S)
    op.add_column("source_registry", sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=True), schema=S)
    op.execute(f"UPDATE {S}.source_registry SET last_processed_at = last_success_at")
    op.execute(f"""
        UPDATE {S}.source_registry SET adapter_key = CASE
            WHEN lower(domain) LIKE '%superindo%' THEN 'superindo'
            WHEN lower(domain) LIKE '%indomaret%' THEN 'indomaret'
            WHEN lower(domain) LIKE '%alfamart%' OR lower(domain) LIKE '%alfagift%' THEN 'alfamart'
            ELSE 'generic_catalog' END
    """)
    # The per-source interval was never honoured before; keep today's effective (daily) behaviour.
    op.execute(f"UPDATE {S}.source_registry SET crawl_frequency_minutes = 1440 WHERE crawl_frequency_minutes < 1440")
    op.create_check_constraint("ck_source_approval", "source_registry",
                               "approval_status IN ('CANDIDATE','APPROVED','REJECTED')", schema=S)

    # ---- scan history
    op.create_table(
        "scan_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="CLI"),
        sa.Column("triggered_by", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="RUNNING"),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        schema=S,
    )
    op.create_index("idx_scan_runs_started", "scan_runs", ["started_at"], schema=S)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'competitor_intel_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {S}.scan_runs TO competitor_intel_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("scan_runs", schema=S)
    op.drop_constraint("ck_source_approval", "source_registry", schema=S, type_="check")
    op.drop_column("source_registry", "last_processed_at", schema=S)
    op.drop_column("source_registry", "adapter_key", schema=S)
    op.drop_column("source_registry", "approval_status", schema=S)
    op.drop_index("idx_promotions_geo_region", "promotions", schema=S)
    op.drop_index("idx_promotions_last_verified", "promotions", schema=S)
    op.drop_index("ix_promotions_source_id", "promotions", schema=S)
    op.drop_constraint("fk_promotions_source", "promotions", schema=S, type_="foreignkey")
    op.drop_column("promotions", "source_id", schema=S)
    op.drop_column("promotions", "last_verified_at", schema=S)
    op.drop_column("promotions", "geography_region", schema=S)
    op.execute(f"UPDATE {S}.promotions SET geography = 'Indonesia' WHERE geography IS NULL")
    op.alter_column("promotions", "geography", schema=S, type_=sa.String(50), nullable=False)
