"""add worker is_active

Revision ID: 3a2af0b7b8f4
Revises: 1b7c88d89f4d
Create Date: 2024-06-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3a2af0b7b8f4"
down_revision = "1b7c88d89f4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workers",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("workers", "is_active")
