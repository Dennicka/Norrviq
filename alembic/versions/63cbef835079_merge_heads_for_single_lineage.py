"""merge_heads_for_single_lineage

Revision ID: 63cbef835079
Revises: 4c9c1a5f3f2c, c1d2e3f4a5b6
Create Date: 2026-02-21

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "63cbef835079"
down_revision: Union[str, Sequence[str], None] = ("4c9c1a5f3f2c", "c1d2e3f4a5b6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
