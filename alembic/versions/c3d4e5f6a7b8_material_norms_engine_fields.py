"""material norms engine fields

Revision ID: c3d4e5f6a7b8
Revises: a91b2c3d4e5f
Create Date: 2026-02-24 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "a91b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("material_consumption_norms", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("material_consumption_norms", sa.Column("work_type_code", sa.String(length=100), nullable=True))
    op.add_column("material_consumption_norms", sa.Column("material_catalog_item_id", sa.Integer(), nullable=True))
    op.add_column("material_consumption_norms", sa.Column("consumption_qty", sa.Numeric(12, 4), nullable=True))
    op.add_column("material_consumption_norms", sa.Column("per_basis_qty", sa.Numeric(12, 4), nullable=True))
    op.add_column("material_consumption_norms", sa.Column("per_basis_unit", sa.String(length=20), nullable=True))
    op.add_column("material_consumption_norms", sa.Column("layers_multiplier_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("material_consumption_norms", sa.Column("allow_fractional", sa.Boolean(), nullable=True))
    op.create_index("ix_material_consumption_norms_work_type_code", "material_consumption_norms", ["work_type_code"])


def downgrade() -> None:
    op.drop_index("ix_material_consumption_norms_work_type_code", table_name="material_consumption_norms")
    op.drop_column("material_consumption_norms", "allow_fractional")
    op.drop_column("material_consumption_norms", "layers_multiplier_enabled")
    op.drop_column("material_consumption_norms", "per_basis_unit")
    op.drop_column("material_consumption_norms", "per_basis_qty")
    op.drop_column("material_consumption_norms", "consumption_qty")
    op.drop_column("material_consumption_norms", "material_catalog_item_id")
    op.drop_column("material_consumption_norms", "work_type_code")
    op.drop_column("material_consumption_norms", "name")
