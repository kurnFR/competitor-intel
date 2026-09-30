"""Add users, login sessions and audit log.

Revision ID: b1c2d3e4f501
Revises: a8c4e1f9d2b7
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b1c2d3e4f501"
down_revision = "a8c4e1f9d2b7"
branch_labels = None
depends_on = None

SCHEMA = "competitor_intel"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="VIEWER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("role IN ('VIEWER','ANALYST','ADMIN')", name="ck_users_role"),
        schema=SCHEMA,
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        schema=SCHEMA,
    )
    op.create_index("idx_user_sessions_user", "user_sessions", ["user_id"], schema=SCHEMA)
    op.create_index("idx_user_sessions_expires", "user_sessions", ["expires_at"], schema=SCHEMA)
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("idx_audit_log_time", "audit_log", ["occurred_at"], schema=SCHEMA)
    # Let the application role use the new tables when it exists (owner/app roles are split).
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'competitor_intel_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.users, {SCHEMA}.user_sessions, {SCHEMA}.audit_log
              TO competitor_intel_app;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("audit_log", schema=SCHEMA)
    op.drop_table("user_sessions", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
