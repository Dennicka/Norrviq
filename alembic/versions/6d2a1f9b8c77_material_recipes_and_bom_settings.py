"""material recipes and project material settings

Revision ID: 6d2a1f9b8c77
Revises: 5e1f7c2a9d10
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "6d2a1f9b8c77"
down_revision = "5e1f7c2a9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("materials") as batch_op:
        batch_op.add_column(sa.Column("sku", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("default_pack_size", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("default_cost_per_unit_ex_vat", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("default_sell_per_unit_ex_vat", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("default_markup_pct", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(sa.Column("vat_rate_pct", sa.Numeric(5, 2), nullable=False, server_default="25.00"))

    op.create_table(
        "material_recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("applies_to", sa.String(length=20), nullable=False, server_default="PROJECT"),
        sa.Column("work_type_id", sa.Integer(), nullable=True),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("consumption_per_m2", sa.Numeric(12, 4), nullable=False),
        sa.Column("coats_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("waste_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("rounding_mode", sa.String(length=20), nullable=False, server_default="NONE"),
        sa.Column("pack_size_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "(applies_to = 'WORKTYPE' AND work_type_id IS NOT NULL) OR (applies_to = 'PROJECT' AND work_type_id IS NULL)",
            name="ck_material_recipes_applies_to_work_type",
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_material_recipes_id"), "material_recipes", ["id"], unique=False)

    op.create_table(
        "project_material_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("default_markup_pct", sa.Numeric(5, 2), nullable=False, server_default="20.00"),
        sa.Column("use_material_sell_price", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("include_materials_in_pricing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(op.f("ix_project_material_settings_id"), "project_material_settings", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_material_settings_id"), table_name="project_material_settings")
    op.drop_table("project_material_settings")
    op.drop_index(op.f("ix_material_recipes_id"), table_name="material_recipes")
    op.drop_table("material_recipes")

    with op.batch_alter_table("materials") as batch_op:
        batch_op.drop_column("vat_rate_pct")
        batch_op.drop_column("default_markup_pct")
        batch_op.drop_column("default_sell_per_unit_ex_vat")
        batch_op.drop_column("default_cost_per_unit_ex_vat")
        batch_op.drop_column("default_pack_size")
        batch_op.drop_column("sku")
