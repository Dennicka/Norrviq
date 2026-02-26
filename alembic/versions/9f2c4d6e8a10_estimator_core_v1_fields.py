"""estimator core v1 fields

Revision ID: 9f2c4d6e8a10
Revises: 578f3ba183f5
Create Date: 2026-02-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f2c4d6e8a10"
down_revision = "578f3ba183f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_work_items", sa.Column("basis_type", sa.String(length=32), nullable=False, server_default="floor_area_m2"))
    op.add_column("project_work_items", sa.Column("selected_room_ids_json", sa.Text(), nullable=True))
    op.add_column("project_work_items", sa.Column("manual_qty", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("calculated_qty", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("project_work_items", sa.Column("calculated_sell_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("project_work_items", sa.Column("calculated_labour_cost_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("project_work_items", sa.Column("unit_rate_ex_vat", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("fixed_total_ex_vat", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("hourly_rate_ex_vat", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_work_items", sa.Column("norm_hours_per_unit", sa.Numeric(12, 4), nullable=True))

    op.execute("UPDATE project_work_items SET scope_mode='room' WHERE scope_mode IS NULL")
    op.execute("UPDATE project_work_items SET basis_type='floor_area_m2' WHERE basis_type IS NULL")
    op.execute("UPDATE project_work_items SET pricing_mode='hourly' WHERE pricing_mode IS NULL")


def downgrade() -> None:
    op.drop_column("project_work_items", "norm_hours_per_unit")
    op.drop_column("project_work_items", "hourly_rate_ex_vat")
    op.drop_column("project_work_items", "fixed_total_ex_vat")
    op.drop_column("project_work_items", "unit_rate_ex_vat")
    op.drop_column("project_work_items", "calculated_labour_cost_ex_vat")
    op.drop_column("project_work_items", "calculated_sell_ex_vat")
    op.drop_column("project_work_items", "calculated_qty")
    op.drop_column("project_work_items", "manual_qty")
    op.drop_column("project_work_items", "selected_room_ids_json")
    op.drop_column("project_work_items", "basis_type")
