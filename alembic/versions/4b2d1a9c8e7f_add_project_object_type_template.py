"""add project object type and template

Revision ID: 4b2d1a9c8e7f
Revises: 0f9a8b7c6d5e
Create Date: 2026-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4b2d1a9c8e7f"
down_revision = "0f9a8b7c6d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("object_type", sa.String(length=32), nullable=True))
    op.add_column("projects", sa.Column("object_template", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "object_template")
    op.drop_column("projects", "object_type")
