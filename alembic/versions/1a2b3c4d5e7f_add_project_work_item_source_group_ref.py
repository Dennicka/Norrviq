"""add project work item source group ref

Revision ID: 1a2b3c4d5e7f
Revises: 4f7a9c2d1b3e
Create Date: 2026-02-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e7f"
down_revision = "4f7a9c2d1b3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_work_items", sa.Column("source_group_ref", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("project_work_items", "source_group_ref")
