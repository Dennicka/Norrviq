"""add package source fields to work items

Revision ID: 7c1e4f2a9b6d
Revises: 4b2d1a9c8e7f
Create Date: 2026-03-01 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "7c1e4f2a9b6d"
down_revision = "4b2d1a9c8e7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_work_items", sa.Column("source_package_code", sa.String(length=64), nullable=True))
    op.add_column("project_work_items", sa.Column("source_package_version", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_project_work_items_source_package_code"), "project_work_items", ["source_package_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_work_items_source_package_code"), table_name="project_work_items")
    op.drop_column("project_work_items", "source_package_version")
    op.drop_column("project_work_items", "source_package_code")
