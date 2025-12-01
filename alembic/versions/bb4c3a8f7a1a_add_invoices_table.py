"""add invoices table

Revision ID: bb4c3a8f7a1a
Revises: 1b7c88d89f4d
Create Date: 2025-05-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "bb4c3a8f7a1a"
down_revision = "9e1b4f3c1234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.String(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("work_sum_without_moms", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("moms_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("rot_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("client_pays_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invoices_id"), "invoices", ["id"], unique=False)
    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoices_invoice_number"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_id"), table_name="invoices")
    op.drop_table("invoices")
