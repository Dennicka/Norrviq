"""merge_heads_single_lineage

Revision ID: 578f3ba183f5
Revises: a7b8c9d0e1f2, f2a3b4c5d6e7
Create Date: 2026-02-26 05:59:04.110652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '578f3ba183f5'
down_revision: Union[str, None] = ('a7b8c9d0e1f2', 'f2a3b4c5d6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
