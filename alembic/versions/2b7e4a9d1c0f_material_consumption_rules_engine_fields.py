"""add material consumption rule engine fields

Revision ID: 2b7e4a9d1c0f
Revises: 1a2b3c4d5e7f
Create Date: 2026-02-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "2b7e4a9d1c0f"
down_revision = "1a2b3c4d5e7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("material_consumption_norms") as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("work_kind", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("basis_type", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("quantity_per_basis", sa.Numeric(12, 4), nullable=True))
        batch_op.add_column(sa.Column("basis_unit", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("waste_factor_pct", sa.Numeric(6, 2), nullable=True))
        batch_op.create_index("ix_material_consumption_norms_work_kind", ["work_kind"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("material_consumption_norms") as batch_op:
        batch_op.drop_index("ix_material_consumption_norms_work_kind")
        batch_op.drop_column("waste_factor_pct")
        batch_op.drop_column("basis_unit")
        batch_op.drop_column("quantity_per_basis")
        batch_op.drop_column("basis_type")
        batch_op.drop_column("work_kind")
        batch_op.drop_column("is_active")
