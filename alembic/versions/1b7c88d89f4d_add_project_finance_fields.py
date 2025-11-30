"""add project finance fields

Revision ID: 1b7c88d89f4d
Revises: f0b5f4df2f5a
Create Date: 2025-02-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1b7c88d89f4d"
down_revision = "f0b5f4df2f5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("salary_fund", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column(
        "projects", sa.Column("employer_taxes", sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        "projects", sa.Column("total_salary_cost", sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column("projects", sa.Column("materials_cost", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("fuel_cost", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("parking_cost", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("rent_cost", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("other_cost", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("overhead_amount", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("total_cost", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("profit", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("projects", sa.Column("margin_percent", sa.Numeric(precision=6, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "margin_percent")
    op.drop_column("projects", "profit")
    op.drop_column("projects", "total_cost")
    op.drop_column("projects", "overhead_amount")
    op.drop_column("projects", "other_cost")
    op.drop_column("projects", "rent_cost")
    op.drop_column("projects", "parking_cost")
    op.drop_column("projects", "fuel_cost")
    op.drop_column("projects", "materials_cost")
    op.drop_column("projects", "total_salary_cost")
    op.drop_column("projects", "employer_taxes")
    op.drop_column("projects", "salary_fund")
