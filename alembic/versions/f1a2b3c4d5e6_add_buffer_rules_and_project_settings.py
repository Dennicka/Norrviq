"""add buffer rules and project buffer settings

Revision ID: f1a2b3c4d5e6
Revises: c9f3a4b8d211
Create Date: 2026-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'c9f3a4b8d211'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'buffer_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('basis', sa.String(length=24), nullable=False),
        sa.Column('unit', sa.String(length=16), nullable=False),
        sa.Column('value', sa.Numeric(12, 2), nullable=False),
        sa.Column('scope_type', sa.String(length=16), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL) OR (scope_type != 'GLOBAL' AND scope_id IS NOT NULL)",
            name='ck_buffer_rules_scope',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_buffer_rules_id'), 'buffer_rules', ['id'], unique=False)

    op.create_table(
        'project_buffer_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('include_setup_cleanup_travel', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('include_risk', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id'),
    )
    op.create_index(op.f('ix_project_buffer_settings_id'), 'project_buffer_settings', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_project_buffer_settings_id'), table_name='project_buffer_settings')
    op.drop_table('project_buffer_settings')
    op.drop_index(op.f('ix_buffer_rules_id'), table_name='buffer_rules')
    op.drop_table('buffer_rules')
