"""materials actuals workflow

Revision ID: 8d1a2b3c4d5e
Revises: c1d2e3f4a5b6,3d2a1c4b5e6f,6d2a1f9b8c77,4c9c1a5f3f2c,d4f6e8a1b2c3
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa


revision = "8d1a2b3c4d5e"
down_revision = ("c1d2e3f4a5b6", "3d2a1c4b5e6f", "6d2a1f9b8c77", "4c9c1a5f3f2c", "d4f6e8a1b2c3")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_material_settings", sa.Column("use_actual_material_costs", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "material_purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("purchased_at", sa.DateTime(), nullable=False),
        sa.Column("invoice_ref", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="SEK"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_material_purchase_project_idempotency"),
    )
    op.create_index(op.f("ix_material_purchases_id"), "material_purchases", ["id"], unique=False)

    op.create_table(
        "material_purchase_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("packs_count", sa.Numeric(12, 2), nullable=False),
        sa.Column("pack_size", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("pack_price_ex_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_rate_pct", sa.Numeric(5, 2), nullable=False, server_default="25.00"),
        sa.Column("line_cost_ex_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_cost_inc_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="MANUAL"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["purchase_id"], ["material_purchases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("packs_count > 0", name="ck_purchase_lines_packs_count_gt_zero"),
        sa.CheckConstraint("pack_size > 0", name="ck_purchase_lines_pack_size_gt_zero"),
        sa.CheckConstraint("pack_price_ex_vat >= 0", name="ck_purchase_lines_pack_price_non_negative"),
    )
    op.create_index(op.f("ix_material_purchase_lines_id"), "material_purchase_lines", ["id"], unique=False)

    op.create_table(
        "project_material_actuals",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("actual_cost_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("actual_cost_inc_vat", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "project_material_stock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("qty_in_base_unit", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "material_id", name="uq_project_material_stock_project_material"),
    )
    op.create_index(op.f("ix_project_material_stock_id"), "project_material_stock", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_material_stock_id"), table_name="project_material_stock")
    op.drop_table("project_material_stock")
    op.drop_table("project_material_actuals")
    op.drop_index(op.f("ix_material_purchase_lines_id"), table_name="material_purchase_lines")
    op.drop_table("material_purchase_lines")
    op.drop_index(op.f("ix_material_purchases_id"), table_name="material_purchases")
    op.drop_table("material_purchases")
    op.drop_column("project_material_settings", "use_actual_material_costs")
