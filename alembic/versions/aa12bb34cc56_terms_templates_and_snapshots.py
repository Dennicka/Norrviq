"""terms templates and snapshot fields

Revision ID: aa12bb34cc56
Revises: e7a1d9c3b4f2
Create Date: 2026-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "aa12bb34cc56"
down_revision = "e7a1d9c3b4f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terms_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("segment", sa.String(length=16), nullable=False),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False, server_default="sv"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "segment",
            "doc_type",
            "lang",
            "version",
            name="uq_terms_templates_segment_doc_lang_version",
        ),
    )
    op.create_index(op.f("ix_terms_templates_id"), "terms_templates", ["id"], unique=False)

    with op.batch_alter_table("company_profile") as batch_op:
        batch_op.add_column(sa.Column("default_offer_terms_template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("default_invoice_terms_template_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_company_profile_default_offer_terms_template_id",
            "terms_templates",
            ["default_offer_terms_template_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_company_profile_default_invoice_terms_template_id",
            "terms_templates",
            ["default_invoice_terms_template_id"],
            ["id"],
        )

    with op.batch_alter_table("clients") as batch_op:
        batch_op.add_column(sa.Column("client_segment", sa.String(length=8), nullable=False, server_default="B2C"))

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("offer_terms_snapshot_title", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("offer_terms_snapshot_body", sa.Text(), nullable=True))

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("invoice_terms_snapshot_title", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("invoice_terms_snapshot_body", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_column("invoice_terms_snapshot_body")
        batch_op.drop_column("invoice_terms_snapshot_title")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("offer_terms_snapshot_body")
        batch_op.drop_column("offer_terms_snapshot_title")

    with op.batch_alter_table("clients") as batch_op:
        batch_op.drop_column("client_segment")

    with op.batch_alter_table("company_profile") as batch_op:
        batch_op.drop_constraint("fk_company_profile_default_invoice_terms_template_id", type_="foreignkey")
        batch_op.drop_constraint("fk_company_profile_default_offer_terms_template_id", type_="foreignkey")
        batch_op.drop_column("default_invoice_terms_template_id")
        batch_op.drop_column("default_offer_terms_template_id")

    op.drop_index(op.f("ix_terms_templates_id"), table_name="terms_templates")
    op.drop_table("terms_templates")
