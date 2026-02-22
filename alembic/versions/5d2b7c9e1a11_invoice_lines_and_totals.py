"""invoice lines and invoice totals

Revision ID: 5d2b7c9e1a11
Revises: 2f8a9c1d4e6b
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5d2b7c9e1a11"
down_revision = "2f8a9c1d4e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="1.00"),
        sa.Column("unit_price_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("line_total_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("vat_rate_pct", sa.Numeric(5, 2), nullable=False, server_default="25.00"),
        sa.Column("vat_amount", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("line_total_inc_vat", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("source_type", sa.String(length=20), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id", "position", name="uq_invoice_lines_invoice_position"),
    )
    op.create_index(op.f("ix_invoice_lines_id"), "invoice_lines", ["id"], unique=False)
    op.create_index(op.f("ix_invoice_lines_invoice_id"), "invoice_lines", ["invoice_id"], unique=False)

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("subtotal_ex_vat", sa.Numeric(12, 2), nullable=False, server_default="0.00"))
        batch_op.add_column(sa.Column("vat_total", sa.Numeric(12, 2), nullable=False, server_default="0.00"))
        batch_op.add_column(sa.Column("total_inc_vat", sa.Numeric(12, 2), nullable=False, server_default="0.00"))


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_column("total_inc_vat")
        batch_op.drop_column("vat_total")
        batch_op.drop_column("subtotal_ex_vat")

    op.drop_index(op.f("ix_invoice_lines_invoice_id"), table_name="invoice_lines")
    op.drop_index(op.f("ix_invoice_lines_id"), table_name="invoice_lines")
    op.drop_table("invoice_lines")
