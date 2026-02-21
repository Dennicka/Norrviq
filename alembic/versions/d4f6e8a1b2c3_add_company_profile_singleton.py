"""add company profile singleton

Revision ID: d4f6e8a1b2c3
Revises: 63cbef835079
Create Date: 2026-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4f6e8a1b2c3"
down_revision = "63cbef835079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False, server_default="Trenor Måleri AB"),
        sa.Column("org_number", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("vat_number", sa.String(length=64), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("city", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=128), nullable=False, server_default="Sverige"),
        sa.Column("email", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("bankgiro", sa.String(length=64), nullable=True),
        sa.Column("plusgiro", sa.String(length=64), nullable=True),
        sa.Column("iban", sa.String(length=64), nullable=True),
        sa.Column("bic", sa.String(length=64), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("invoice_prefix", sa.String(length=16), nullable=False, server_default="TR-"),
        sa.Column("offer_prefix", sa.String(length=16), nullable=False, server_default="OF-"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO company_profile (
                id, legal_name, org_number, address_line1, postal_code, city, country, email,
                payment_terms_days, invoice_prefix, offer_prefix
            )
            SELECT 1, 'Trenor Måleri AB', '', '', '', '', 'Sverige', '', 10, 'TR-', 'OF-'
            WHERE NOT EXISTS (SELECT 1 FROM company_profile WHERE id = 1)
            """
        )
    )


def downgrade() -> None:
    op.drop_table("company_profile")
