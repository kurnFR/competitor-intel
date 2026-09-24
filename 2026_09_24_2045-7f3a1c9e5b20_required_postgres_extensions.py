"""ensure PostgreSQL extensions required by competitor intelligence are available

Revision ID: 7f3a1c9e5b20
Revises: 6e2a9b4c1d73
Create Date: 2026-09-24 20:45:00+07:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "7f3a1c9e5b20"
down_revision: Union[str, None] = "6e2a9b4c1d73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Both extensions are database-level prerequisites used by the application.
    # Migration credentials are expected to have the required PostgreSQL
    # privilege; the application role does not need to own the extensions.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')


def downgrade() -> None:
    # Extensions are database-level resources and may be shared by other
    # schemas. Do not remove them during an application migration downgrade.
    pass
