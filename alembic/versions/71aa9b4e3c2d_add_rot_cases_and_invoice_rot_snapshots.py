"""add rot cases and invoice rot snapshots

Revision ID: 71aa9b4e3c2d
Revises: 6c1d2e3f4a5b
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "71aa9b4e3c2d"
down_revision = "6c1d2e3f4a5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("labour_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("material_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("other_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("rot_snapshot_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("invoices", sa.Column("rot_snapshot_pct", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("rot_snapshot_eligible_labor_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("invoices", sa.Column("rot_snapshot_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))

    op.create_table(
        "rot_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("eligible_labor_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("rot_pct", sa.Numeric(5, 2), nullable=False, server_default="30"),
        sa.Column("rot_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("customer_personnummer", sa.Text(), nullable=True),
        sa.Column("property_identifier", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id"),
    )
    op.create_index(op.f("ix_rot_cases_id"), "rot_cases", ["id"], unique=False)
    op.create_index(op.f("ix_rot_cases_invoice_id"), "rot_cases", ["invoice_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_rot_cases_invoice_id"), table_name="rot_cases")
    op.drop_index(op.f("ix_rot_cases_id"), table_name="rot_cases")
    op.drop_table("rot_cases")

    op.drop_column("invoices", "rot_snapshot_amount")
    op.drop_column("invoices", "rot_snapshot_eligible_labor_ex_vat")
    op.drop_column("invoices", "rot_snapshot_pct")
    op.drop_column("invoices", "rot_snapshot_enabled")
    op.drop_column("invoices", "other_ex_vat")
    op.drop_column("invoices", "material_ex_vat")
    op.drop_column("invoices", "labour_ex_vat")
