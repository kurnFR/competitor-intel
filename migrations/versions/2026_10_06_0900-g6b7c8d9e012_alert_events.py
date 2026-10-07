"""Alert events (scan/source failures announced once each).

Revision ID: g6b7c8d9e012
Revises: f5a6b7c8d901
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "g6b7c8d9e012"
down_revision = "f5a6b7c8d901"
branch_labels = None
depends_on = None

S = "competitor_intel"


def upgrade() -> None:
    op.create_table(
        "alert_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("fingerprint", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery", sa.String(120), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("fingerprint", name="uq_alert_events_fingerprint"),
        schema=S,
    )
    op.create_index("idx_alert_events_created", "alert_events", ["created_at"], schema=S)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'competitor_intel_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {S}.alert_events TO competitor_intel_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("alert_events", schema=S)
