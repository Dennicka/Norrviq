"""add speed profiles and execution settings

Revision ID: ab12cd34ef56
Revises: f1a2b3c4d5e6
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab12cd34ef56'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'speed_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name_ru', sa.String(length=255), nullable=False),
        sa.Column('name_sv', sa.String(length=255), nullable=False),
        sa.Column('multiplier', sa.Numeric(6, 3), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index(op.f('ix_speed_profiles_id'), 'speed_profiles', ['id'], unique=False)

    op.create_table(
        'project_execution_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('speed_profile_id', sa.Integer(), nullable=True),
        sa.Column('apply_scope', sa.String(length=32), nullable=False, server_default='PROJECT'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['speed_profile_id'], ['speed_profiles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id'),
    )
    op.create_index(op.f('ix_project_execution_profiles_id'), 'project_execution_profiles', ['id'], unique=False)

    with op.batch_alter_table('workers') as batch_op:
        batch_op.add_column(sa.Column('default_speed_profile_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workers_default_speed_profile_id', 'speed_profiles', ['default_speed_profile_id'], ['id'])

    op.bulk_insert(
        sa.table(
            'speed_profiles',
            sa.column('code', sa.String()),
            sa.column('name_ru', sa.String()),
            sa.column('name_sv', sa.String()),
            sa.column('multiplier', sa.Numeric()),
            sa.column('is_active', sa.Boolean()),
        ),
        [
            {'code': 'SLOW', 'name_ru': 'Медленно', 'name_sv': 'Långsam', 'multiplier': 1.200, 'is_active': True},
            {'code': 'MEDIUM', 'name_ru': 'Средне', 'name_sv': 'Normal', 'multiplier': 1.000, 'is_active': True},
            {'code': 'FAST', 'name_ru': 'Быстро', 'name_sv': 'Snabb', 'multiplier': 0.850, 'is_active': True},
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table('workers') as batch_op:
        batch_op.drop_constraint('fk_workers_default_speed_profile_id', type_='foreignkey')
        batch_op.drop_column('default_speed_profile_id')
    op.drop_index(op.f('ix_project_execution_profiles_id'), table_name='project_execution_profiles')
    op.drop_table('project_execution_profiles')
    op.drop_index(op.f('ix_speed_profiles_id'), table_name='speed_profiles')
    op.drop_table('speed_profiles')
