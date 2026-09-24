"""Bootstrap the current competitor_intel schema.

This repository is still pre-production. The schema is defined by the SQLAlchemy
models and this migration creates that schema in an empty competitor_intel
database. Once the first production database exists, subsequent changes must use
explicit forward-only Alembic migrations rather than editing this file.
"""

from alembic import op
from sqlalchemy import text

from app.models import Base


revision = "20260924_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("CREATE SCHEMA IF NOT EXISTS competitor_intel"))
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
    bind.execute(text("DROP SCHEMA IF EXISTS competitor_intel CASCADE"))
