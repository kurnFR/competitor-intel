"""bootstrap competitor_intel schema from declarative models

Revision ID: 20260923_01
Revises:
Create Date: 2026-09-23

This is the first migration in the project. It intentionally bootstraps the
empty competitor_intel database from SQLAlchemy metadata. Subsequent schema
changes must use explicit Alembic migrations and must not rely on create_all.
"""

from alembic import op
from app.models import Base

revision = "20260923_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
