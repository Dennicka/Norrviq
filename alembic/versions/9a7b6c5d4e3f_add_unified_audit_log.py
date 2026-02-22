"""add unified audit log

Revision ID: 9a7b6c5d4e3f
Revises: 71aa9b4e3c2d
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "9a7b6c5d4e3f"
down_revision = "71aa9b4e3c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_role", sa.String(length=20), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("severity", sa.Enum("INFO", "WARN", "SECURITY", name="auditseverity"), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index("ix_audit_log_action", "audit_log", ["action"], unique=False)
    op.create_index("ix_audit_log_request_id", "audit_log", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_request_id", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.execute("DROP TYPE IF EXISTS auditseverity")
