"""add project dates, materials, and worktype activity

Revision ID: a1b2c3d4e5f6
Revises: 3a2af0b7b8f4
Create Date: 2025-02-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "3a2af0b7b8f4"
branch_labels = None
depends_on = None


FK_NAME = "project_cost_items_material_id_fkey"


def upgrade() -> None:
    op.add_column("projects", sa.Column("planned_start_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("planned_end_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("actual_start_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("actual_end_date", sa.Date(), nullable=True))

    op.add_column(
        "work_types",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name_ru", sa.String(), nullable=False),
        sa.Column("name_sv", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("default_price_per_unit", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("moms_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("comment", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_materials_code"), "materials", ["code"], unique=False)
    op.create_index(op.f("ix_materials_id"), "materials", ["id"], unique=False)

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("project_cost_items") as batch_op:
            batch_op.add_column(sa.Column("material_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(FK_NAME, "materials", ["material_id"], ["id"])
    else:
        op.add_column("project_cost_items", sa.Column("material_id", sa.Integer(), nullable=True))
        op.create_foreign_key(FK_NAME, "project_cost_items", "materials", ["material_id"], ["id"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("project_cost_items") as batch_op:
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
            batch_op.drop_column("material_id")
    else:
        op.drop_constraint(FK_NAME, "project_cost_items", type_="foreignkey")
        op.drop_column("project_cost_items", "material_id")

    op.drop_index(op.f("ix_materials_id"), table_name="materials")
    op.drop_index(op.f("ix_materials_code"), table_name="materials")
    op.drop_table("materials")

    op.drop_column("work_types", "is_active")

    op.drop_column("projects", "actual_end_date")
    op.drop_column("projects", "actual_start_date")
    op.drop_column("projects", "planned_end_date")
    op.drop_column("projects", "planned_start_date")
