"""add db backups table

Revision ID: 3b1d4a5f6c7e
Revises: 9a7b6c5d4e3f
Create Date: 2026-02-22 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '3b1d4a5f6c7e'
down_revision = '9a7b6c5d4e3f'
branch_labels = None
depends_on = None


backup_status_enum = sa.Enum('OK', 'FAILED', name='backupstatus')


def upgrade() -> None:
    backup_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'db_backups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', backup_status_enum, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename'),
    )
    op.create_index(op.f('ix_db_backups_created_at'), 'db_backups', ['created_at'], unique=False)
    op.create_index(op.f('ix_db_backups_id'), 'db_backups', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_db_backups_id'), table_name='db_backups')
    op.drop_index(op.f('ix_db_backups_created_at'), table_name='db_backups')
    op.drop_table('db_backups')
    backup_status_enum.drop(op.get_bind(), checkfirst=True)
