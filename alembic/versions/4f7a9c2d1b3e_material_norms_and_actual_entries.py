"""material norms and actual entries

Revision ID: 4f7a9c2d1b3e
Revises: 3e5f7a9b1c2d
Create Date: 2026-02-23 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4f7a9c2d1b3e"
down_revision = "3e5f7a9b1c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_consumption_norms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("material_name", sa.String(length=255), nullable=False),
        sa.Column("material_category", sa.String(length=100), nullable=False, server_default="other"),
        sa.Column("applies_to_work_type", sa.String(length=100), nullable=False),
        sa.Column("surface_type", sa.String(length=20), nullable=False, server_default="custom"),
        sa.Column("consumption_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("consumption_unit", sa.String(length=20), nullable=False, server_default="per_1_m2"),
        sa.Column("material_unit", sa.String(length=20), nullable=False, server_default="pcs"),
        sa.Column("package_size", sa.Numeric(12, 4), nullable=True),
        sa.Column("package_unit", sa.String(length=20), nullable=True),
        sa.Column("waste_percent", sa.Numeric(6, 2), nullable=False, server_default="10"),
        sa.Column("coats_multiplier_mode", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("brand_product", sa.String(length=255), nullable=True),
        sa.Column("default_unit_price_sek", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_material_consumption_norms_applies_to_work_type", "material_consumption_norms", ["applies_to_work_type"])

    op.create_table(
        "project_material_actual_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_name", sa.String(length=255), nullable=False),
        sa.Column("actual_qty", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("actual_packages", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("actual_cost_sek", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("supplier", sa.String(length=255), nullable=True),
        sa.Column("receipt_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_project_material_actual_entries_project_id", "project_material_actual_entries", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_material_actual_entries_project_id", table_name="project_material_actual_entries")
    op.drop_table("project_material_actual_entries")
    op.drop_index("ix_material_consumption_norms_applies_to_work_type", table_name="material_consumption_norms")
    op.drop_table("material_consumption_norms")
