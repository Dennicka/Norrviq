"""add completeness rules

Revision ID: 2f8a9c1d4e6b
Revises: 7c3d9e1a2b44
Create Date: 2026-02-22 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '2f8a9c1d4e6b'
down_revision = '7c3d9e1a2b44'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'completeness_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('segment', sa.String(length=16), nullable=False, server_default='ANY'),
        sa.Column('pricing_mode', sa.String(length=32), nullable=False, server_default='ANY'),
        sa.Column('check_key', sa.String(length=128), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('severity', sa.String(length=16), nullable=False, server_default='WARNING'),
        sa.Column('message_ru', sa.Text(), nullable=False),
        sa.Column('message_sv', sa.Text(), nullable=False),
        sa.Column('hint_link', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("segment IN ('ANY','B2C','BRF','B2B')", name='ck_completeness_rules_segment'),
        sa.CheckConstraint("pricing_mode IN ('ANY','HOURLY','FIXED_TOTAL','PER_M2','PER_ROOM','PIECEWORK')", name='ck_completeness_rules_pricing_mode'),
        sa.CheckConstraint("severity IN ('INFO','WARNING','BLOCK')", name='ck_completeness_rules_severity'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_completeness_rules_id'), 'completeness_rules', ['id'], unique=False)

    op.add_column('pricing_policy', sa.Column('min_completeness_score_for_fixed', sa.Integer(), nullable=False, server_default='70'))
    op.add_column('pricing_policy', sa.Column('min_completeness_score_for_per_m2', sa.Integer(), nullable=False, server_default='60'))
    op.add_column('pricing_policy', sa.Column('min_completeness_score_for_per_room', sa.Integer(), nullable=False, server_default='60'))
    op.add_column('pricing_policy', sa.Column('warn_only_below_score', sa.Boolean(), nullable=False, server_default=sa.false()))

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
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_WORK_ITEMS', weight=15, severity='BLOCK', message_ru='Добавьте хотя бы одну работу в смету. Пример: покраска стен 30 м².', message_sv='Lägg till minst en arbetspost i kalkylen, t.ex. målning av vägg 30 m².', hint_link='/projects/{project_id}#work-items'),
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_LABOR_HOURS', weight=10, severity='WARNING', message_ru='Нужны трудозатраты в часах. Проверьте нормы и количества работ.', message_sv='Arbetstimmar saknas. Kontrollera normtider och mängder.', hint_link='/projects/{project_id}/pricing'),
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_BUFFERS_ENABLED', weight=8, severity='WARNING', message_ru='Буферы выключены. Включите setup/cleanup/travel и risk для реалистичной цены.', message_sv='Buffertar är avstängda. Aktivera setup/cleanup/travel och risk.', hint_link='/projects/{project_id}/buffers'),
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_SPEED_PROFILE_SET', weight=7, severity='WARNING', message_ru='Профиль скорости не задан. Выберите speed profile в Buffers.', message_sv='Hastighetsprofil saknas. Välj speed profile under Buffers.', hint_link='/projects/{project_id}/buffers'),
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_COMPANY_PROFILE_FIELDS', weight=10, severity='WARNING', message_ru='Проверьте реквизиты компании: название, org nr, адрес, email.', message_sv='Kontrollera företagsuppgifter: namn, org nr, adress, e-post.', hint_link='/settings/company'),
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_COMPANY_PAYMENT_METHOD', weight=10, severity='BLOCK', message_ru='Добавьте bankgiro/plusgiro/IBAN перед выпуском документов.', message_sv='Lägg till bankgiro/plusgiro/IBAN innan dokument utfärdas.', hint_link='/settings/company'),
            dict(is_active=True, segment='ANY', pricing_mode='ANY', check_key='HAS_TERMS_PAYMENT_DAYS', weight=5, severity='WARNING', message_ru='Проверьте payment terms (дней оплаты) в настройках компании.', message_sv='Kontrollera betalningsvillkor (antal dagar) i företagsinställningar.', hint_link='/settings/company'),
            dict(is_active=True, segment='ANY', pricing_mode='FIXED_TOTAL', check_key='HAS_ROOMS', weight=10, severity='BLOCK', message_ru='Для fixed price нужна структура комнат. Добавьте хотя бы одну комнату.', message_sv='För fastpris behövs rumsstruktur. Lägg till minst ett rum.', hint_link='/projects/{project_id}/rooms/'),
            dict(is_active=True, segment='ANY', pricing_mode='FIXED_TOTAL', check_key='HAS_TOTAL_M2', weight=10, severity='BLOCK', message_ru='Для fixed price нужна общая площадь. Заполните площадь комнат.', message_sv='För fastpris behövs total yta. Fyll i rummens ytor.', hint_link='/projects/{project_id}/rooms/'),
            dict(is_active=True, segment='ANY', pricing_mode='FIXED_TOTAL', check_key='HAS_ROOM_WALL_HEIGHT', weight=5, severity='WARNING', message_ru='Не хватает высоты стен для части комнат. Заполните wall height.', message_sv='Vägg-/takhöjd saknas i vissa rum. Fyll i wall height.', hint_link='/projects/{project_id}/rooms/'),
            dict(is_active=True, segment='ANY', pricing_mode='PER_M2', check_key='HAS_TOTAL_M2', weight=20, severity='BLOCK', message_ru='Режим per m² невозможен без площади. Укажите floor area в комнатах.', message_sv='Läge per m² kräver total yta. Ange floor area i rum.', hint_link='/projects/{project_id}/rooms/'),
            dict(is_active=True, segment='ANY', pricing_mode='PER_ROOM', check_key='HAS_ROOMS', weight=20, severity='BLOCK', message_ru='Режим per room невозможен без комнат. Добавьте комнаты в проект.', message_sv='Läge per rum kräver rum. Lägg till rum i projektet.', hint_link='/projects/{project_id}/rooms/'),
            dict(is_active=True, segment='ANY', pricing_mode='PIECEWORK', check_key='HAS_WORK_ITEMS', weight=20, severity='BLOCK', message_ru='Piecework невозможен без работ. Добавьте work items.', message_sv='Piecework kräver arbetsposter. Lägg till work items.', hint_link='/projects/{project_id}#work-items'),
        ],
    )


def downgrade() -> None:
    op.drop_column('pricing_policy', 'warn_only_below_score')
    op.drop_column('pricing_policy', 'min_completeness_score_for_per_room')
    op.drop_column('pricing_policy', 'min_completeness_score_for_per_m2')
    op.drop_column('pricing_policy', 'min_completeness_score_for_fixed')
    op.drop_index(op.f('ix_completeness_rules_id'), table_name='completeness_rules')
    op.drop_table('completeness_rules')
