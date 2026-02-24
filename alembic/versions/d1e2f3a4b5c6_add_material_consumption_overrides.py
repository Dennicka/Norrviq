"""add material consumption overrides

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-02-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_consumption_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("work_type_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("surface_kind", sa.String(length=20), nullable=False),
        sa.Column("unit_basis", sa.String(length=20), nullable=False),
        sa.Column("quantity_per_unit", sa.Numeric(12, 4), nullable=False),
        sa.Column("base_unit_size", sa.Numeric(12, 4), nullable=False, server_default="1"),
        sa.Column("waste_factor_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_per_unit > 0", name="ck_mco_quantity_per_unit_positive"),
        sa.CheckConstraint("base_unit_size > 0", name="ck_mco_base_unit_size_positive"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "room_id", "work_type_id", "material_id", "surface_kind", "unit_basis", "is_active", name="uq_mco_scope_active"),
    )
    op.create_index(op.f("ix_material_consumption_overrides_id"), "material_consumption_overrides", ["id"], unique=False)
    op.create_index(op.f("ix_material_consumption_overrides_project_id"), "material_consumption_overrides", ["project_id"], unique=False)
    op.create_index(op.f("ix_material_consumption_overrides_room_id"), "material_consumption_overrides", ["room_id"], unique=False)
    op.create_index(op.f("ix_material_consumption_overrides_work_type_id"), "material_consumption_overrides", ["work_type_id"], unique=False)
    op.create_index(op.f("ix_material_consumption_overrides_material_id"), "material_consumption_overrides", ["material_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_material_consumption_overrides_material_id"), table_name="material_consumption_overrides")
    op.drop_index(op.f("ix_material_consumption_overrides_work_type_id"), table_name="material_consumption_overrides")
    op.drop_index(op.f("ix_material_consumption_overrides_room_id"), table_name="material_consumption_overrides")
    op.drop_index(op.f("ix_material_consumption_overrides_project_id"), table_name="material_consumption_overrides")
    op.drop_index(op.f("ix_material_consumption_overrides_id"), table_name="material_consumption_overrides")
    op.drop_table("material_consumption_overrides")
