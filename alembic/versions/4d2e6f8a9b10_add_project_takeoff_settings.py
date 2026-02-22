"""add project takeoff settings

Revision ID: 4d2e6f8a9b10
Revises: 3b1d4a5f6c7e
Create Date: 2026-02-22 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '4d2e6f8a9b10'
down_revision = '3b1d4a5f6c7e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_takeoff_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('m2_basis', sa.String(length=32), nullable=False, server_default='FLOOR_AREA'),
        sa.Column('include_openings_subtraction', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('wall_area_formula_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("m2_basis IN ('FLOOR_AREA','WALL_AREA','CEILING_AREA','PAINTABLE_TOTAL')", name='ck_project_takeoff_settings_m2_basis'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id'),
    )
    op.create_index(op.f('ix_project_takeoff_settings_id'), 'project_takeoff_settings', ['id'], unique=False)

    op.execute(
        """
        INSERT INTO project_takeoff_settings(project_id, m2_basis, include_openings_subtraction, wall_area_formula_version)
        SELECT id, 'FLOOR_AREA', 0, 1 FROM projects
        """
    )

    completeness_rules = sa.table(
        'completeness_rules',
        sa.column('is_active', sa.Boolean()),
        sa.column('segment', sa.String()),
        sa.column('pricing_mode', sa.String()),
        sa.column('check_key', sa.String()),
        sa.column('weight', sa.Integer()),
        sa.column('severity', sa.String()),
        sa.column('message_ru', sa.Text()),
        sa.column('message_sv', sa.Text()),
        sa.column('hint_link', sa.String()),
    )
    op.bulk_insert(
        completeness_rules,
        [
            dict(is_active=True, segment='ANY', pricing_mode='PER_M2', check_key='HAS_PERIMETER_AND_HEIGHT_FOR_WALL_AREA', weight=20, severity='BLOCK', message_ru='Для базы стен/покрашиваемой площади нужны perimeter и height для комнат.', message_sv='För vägg-/målningsbar yta krävs perimeter och höjd för rum.', hint_link='/projects/{project_id}/rooms/'),
            dict(is_active=True, segment='ANY', pricing_mode='PER_M2', check_key='HAS_FLOOR_AREA_FOR_CEILING_OR_FLOOR', weight=20, severity='BLOCK', message_ru='Для базы пол/потолок нужна floor area в комнатах.', message_sv='För golv-/takbas krävs floor area i rummen.', hint_link='/projects/{project_id}/rooms/'),
        ],
    )

    sanity_rules = sa.table(
        'sanity_rules',
        sa.column('is_active', sa.Boolean()),
        sa.column('entity', sa.String()),
        sa.column('field', sa.String()),
        sa.column('rule_type', sa.String()),
        sa.column('min_value', sa.Numeric(12, 2)),
        sa.column('max_value', sa.Numeric(12, 2)),
        sa.column('severity', sa.String()),
        sa.column('message_ru', sa.Text()),
        sa.column('message_sv', sa.Text()),
    )
    op.bulk_insert(
        sanity_rules,
        [
            dict(is_active=True, entity='ROOM', field='wall_perimeter_m', rule_type='MIN_MAX', min_value=2.00, max_value=200.00, severity='WARNING', message_ru='Периметр комнаты обычно 2–200 м. Проверьте ввод.', message_sv='Rumsomkrets brukar vara 2–200 m.'),
            dict(is_active=True, entity='ROOM', field='wall_perimeter_m', rule_type='MIN_MAX', min_value=0.50, max_value=400.00, severity='BLOCK', message_ru='Критично: периметр комнаты вне реалистичного диапазона 0.5–400 м.', message_sv='Kritiskt: rumsomkrets utanför 0,5–400 m.'),
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM completeness_rules WHERE check_key IN ('HAS_PERIMETER_AND_HEIGHT_FOR_WALL_AREA','HAS_FLOOR_AREA_FOR_CEILING_OR_FLOOR')")
    op.execute("DELETE FROM sanity_rules WHERE field='wall_perimeter_m'")
    op.drop_index(op.f('ix_project_takeoff_settings_id'), table_name='project_takeoff_settings')
    op.drop_table('project_takeoff_settings')
