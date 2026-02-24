"""add material catalog items

Revision ID: 3c8d2e1f9a0b
Revises: 2b7e4a9d1c0f
Create Date: 2026-02-24 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "3c8d2e1f9a0b"
down_revision = "2b7e4a9d1c0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_catalog_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("package_size", sa.Numeric(12, 4), nullable=False),
        sa.Column("package_unit", sa.String(length=20), nullable=False),
        sa.Column("price_ex_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("supplier_sku", sa.String(length=100), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("variant", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default_for_material", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("package_size > 0", name="ck_material_catalog_package_size_gt_zero"),
        sa.CheckConstraint("price_ex_vat >= 0", name="ck_material_catalog_price_non_negative"),
        sa.CheckConstraint("vat_rate_pct >= 0 AND vat_rate_pct <= 100", name="ck_material_catalog_vat_range"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_material_catalog_items_id"), "material_catalog_items", ["id"], unique=False)
    op.create_index(op.f("ix_material_catalog_items_material_code"), "material_catalog_items", ["material_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_material_catalog_items_material_code"), table_name="material_catalog_items")
    op.drop_index(op.f("ix_material_catalog_items_id"), table_name="material_catalog_items")
    op.drop_table("material_catalog_items")
