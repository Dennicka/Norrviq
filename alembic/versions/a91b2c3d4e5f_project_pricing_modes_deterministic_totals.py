"""project pricing modes deterministic totals

Revision ID: a91b2c3d4e5f
Revises: 6f2a7b1c9d0e
Create Date: 2026-02-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a91b2c3d4e5f"
down_revision = "6f2a7b1c9d0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_pricing", sa.Column("pricing_mode", sa.String(length=16), nullable=False, server_default="hourly"))
    op.add_column("project_pricing", sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("project_pricing", sa.Column("sqm_rate", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("project_pricing", sa.Column("sqm_basis", sa.String(length=32), nullable=False, server_default="walls_ceilings"))
    op.add_column("project_pricing", sa.Column("sqm_custom_value", sa.Numeric(12, 2), nullable=True))
    op.add_column("project_pricing", sa.Column("fixed_price_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("project_pricing", sa.Column("include_materials_in_sell_price", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("project_pricing", sa.Column("markup_percent", sa.Numeric(8, 2), nullable=False, server_default="0"))
    op.add_column("project_pricing", sa.Column("rounding_mode", sa.String(length=16), nullable=False, server_default="none"))

    op.execute(
        """
        UPDATE project_pricing
        SET
            pricing_mode = CASE mode
                WHEN 'PER_M2' THEN 'per_m2'
                WHEN 'FIXED_TOTAL' THEN 'fixed'
                ELSE 'hourly'
            END,
            hourly_rate = COALESCE(hourly_rate_override, 0),
            sqm_rate = COALESCE(rate_per_m2, 0),
            fixed_price_amount = COALESCE(fixed_total_price, 0),
            include_materials_in_sell_price = include_materials
        """
    )


def downgrade() -> None:
    op.drop_column("project_pricing", "rounding_mode")
    op.drop_column("project_pricing", "markup_percent")
    op.drop_column("project_pricing", "include_materials_in_sell_price")
    op.drop_column("project_pricing", "fixed_price_amount")
    op.drop_column("project_pricing", "sqm_custom_value")
    op.drop_column("project_pricing", "sqm_basis")
    op.drop_column("project_pricing", "sqm_rate")
    op.drop_column("project_pricing", "hourly_rate")
    op.drop_column("project_pricing", "pricing_mode")
