"""invoice material pricing settings

Revision ID: 3d2a1c4b5e6f
Revises: e1f2a3b4c5d6
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3d2a1c4b5e6f"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_procurement_settings", sa.Column("material_pricing_mode", sa.String(length=30), nullable=False, server_default="COST_PLUS_MARKUP"))
    op.add_column("project_procurement_settings", sa.Column("material_markup_pct", sa.Numeric(5, 2), nullable=False, server_default="20.00"))
    op.add_column("project_procurement_settings", sa.Column("round_invoice_materials_to_packs", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("project_procurement_settings", sa.Column("invoice_material_unit", sa.String(length=20), nullable=False, server_default="PACKS"))
    op.add_column("invoices", sa.Column("material_pricing_snapshot", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("material_source_snapshot_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "material_source_snapshot_hash")
    op.drop_column("invoices", "material_pricing_snapshot")
    op.drop_column("project_procurement_settings", "invoice_material_unit")
    op.drop_column("project_procurement_settings", "round_invoice_materials_to_packs")
    op.drop_column("project_procurement_settings", "material_markup_pct")
    op.drop_column("project_procurement_settings", "material_pricing_mode")
