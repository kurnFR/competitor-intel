"""enforce idempotent promotion observations per document

Revision ID: c4a81e6f2b73
Revises: b7e41c2d8f90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4a81e6f2b73"
down_revision: Union[str, None] = "b7e41c2d8f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_promotion_observations_document_promotion",
        "promotion_observations",
        ["document_id", "promotion_id"],
        unique=True,
        schema="competitor_intel",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_promotion_observations_document_promotion",
        table_name="promotion_observations",
        schema="competitor_intel",
    )
