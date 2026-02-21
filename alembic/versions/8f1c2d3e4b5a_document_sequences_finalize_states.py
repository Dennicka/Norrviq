"""document sequences and finalize states

Revision ID: 8f1c2d3e4b5a
Revises: d4f6e8a1b2c3
Create Date: 2026-02-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f1c2d3e4b5a"
down_revision: Union[str, Sequence[str], None] = "d4f6e8a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_type", "year", name="uq_document_sequences_type_year"),
    )
    op.create_index(op.f("ix_document_sequences_id"), "document_sequences", ["id"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_id"), "audit_events", ["id"], unique=False)

    op.add_column("projects", sa.Column("offer_status", sa.String(length=20), nullable=False, server_default="draft"))
    op.add_column("projects", sa.Column("offer_number", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_projects_offer_number"), "projects", ["offer_number"], unique=True)

    op.add_column(
        "company_profile",
        sa.Column("document_number_padding", sa.Integer(), nullable=False, server_default="4"),
    )

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.alter_column("invoice_number", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.alter_column("invoice_number", existing_type=sa.String(), nullable=False)
    op.drop_column("company_profile", "document_number_padding")
    op.drop_index(op.f("ix_projects_offer_number"), table_name="projects")
    op.drop_column("projects", "offer_number")
    op.drop_column("projects", "offer_status")

    op.drop_index(op.f("ix_audit_events_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_document_sequences_id"), table_name="document_sequences")
    op.drop_table("document_sequences")
