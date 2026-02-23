"""add work item pricing modes

Revision ID: 3e5f7a9b1c2d
Revises: 2c4b6d8e9f10
Create Date: 2026-02-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "3e5f7a9b1c2d"
down_revision = "2c4b6d8e9f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("internal_labor_cost_rate_sek", sa.Numeric(10, 2), nullable=False, server_default="300.00"))

    op.add_column("project_work_items", sa.Column("pricing_mode", sa.String(length=20), nullable=False, server_default="hourly"))
    op.add_column("project_work_items", sa.Column("hourly_rate_sek", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("area_rate_sek", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("fixed_price_sek", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("billable_area_m2", sa.Numeric(10, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("labor_cost_sek", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("materials_cost_sek", sa.Numeric(12, 2), nullable=True, server_default="0.00"))
    op.add_column("project_work_items", sa.Column("total_cost_sek", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("margin_sek", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("margin_pct", sa.Numeric(6, 2), nullable=True))

    op.execute("UPDATE project_work_items SET pricing_mode = 'hourly' WHERE pricing_mode IS NULL")


def downgrade() -> None:
    op.drop_column("project_work_items", "margin_pct")
    op.drop_column("project_work_items", "margin_sek")
    op.drop_column("project_work_items", "total_cost_sek")
    op.drop_column("project_work_items", "materials_cost_sek")
    op.drop_column("project_work_items", "labor_cost_sek")
    op.drop_column("project_work_items", "billable_area_m2")
    op.drop_column("project_work_items", "fixed_price_sek")
    op.drop_column("project_work_items", "area_rate_sek")
    op.drop_column("project_work_items", "hourly_rate_sek")
    op.drop_column("project_work_items", "pricing_mode")

    op.drop_column("settings", "internal_labor_cost_rate_sek")
