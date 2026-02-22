"""add offer commercial snapshot

Revision ID: b7c8d9e0f1a2
Revises: 4d2e6f8a9b10
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "4d2e6f8a9b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("offer_commercial_snapshot", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "offer_commercial_snapshot")
