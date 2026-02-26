"""material pack procurement fields

Revision ID: a7b8c9d0e1f2
Revises: e1f2a3b4c5d6, 4d2e6f8a9b10, 2f8a9c1d4e6b
Create Date: 2026-02-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = ("e1f2a3b4c5d6", "4d2e6f8a9b10", "2f8a9c1d4e6b")
branch_labels = None
depends_on = None


material_pack_rounding_rule = sa.Enum("CEIL", "NEAREST", "NONE", name="material_pack_rounding_rule")


def upgrade() -> None:
    bind = op.get_bind()
    material_pack_rounding_rule.create(bind, checkfirst=True)
    op.add_column("materials", sa.Column("pack_size", sa.Numeric(12, 4), nullable=True))
    op.add_column("materials", sa.Column("pack_unit", sa.String(length=20), nullable=True))
    op.add_column("materials", sa.Column("pack_rounding_rule", material_pack_rounding_rule, nullable=False, server_default="CEIL"))
    op.add_column("materials", sa.Column("min_pack_qty", sa.Numeric(12, 2), nullable=False, server_default="1"))
    op.add_column("materials", sa.Column("is_bulk_material", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("materials", "is_bulk_material")
    op.drop_column("materials", "min_pack_qty")
    op.drop_column("materials", "pack_rounding_rule")
    op.drop_column("materials", "pack_unit")
    op.drop_column("materials", "pack_size")
    bind = op.get_bind()
    material_pack_rounding_rule.drop(bind, checkfirst=True)
