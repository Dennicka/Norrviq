"""add sanity rules

Revision ID: 7c3d9e1a2b44
Revises: ab12cd34ef56
Create Date: 2026-02-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c3d9e1a2b44'
down_revision = 'ab12cd34ef56'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sanity_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('entity', sa.String(length=32), nullable=False),
        sa.Column('field', sa.String(length=64), nullable=False),
        sa.Column('rule_type', sa.String(length=32), nullable=False),
        sa.Column('min_value', sa.Numeric(12, 2), nullable=True),
        sa.Column('max_value', sa.Numeric(12, 2), nullable=True),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('message_ru', sa.Text(), nullable=False),
        sa.Column('message_sv', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("entity IN ('ROOM','SURFACE','OPENING','WORK_ITEM','PROJECT')", name='ck_sanity_rules_entity'),
        sa.CheckConstraint("rule_type IN ('MIN_MAX','RATIO_MAX','DELTA_MAX')", name='ck_sanity_rules_rule_type'),
        sa.CheckConstraint("severity IN ('WARNING','BLOCK')", name='ck_sanity_rules_severity'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sanity_rules_id'), 'sanity_rules', ['id'], unique=False)

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
            dict(is_active=True, entity='ROOM', field='wall_height_m', rule_type='MIN_MAX', min_value=2.00, max_value=6.00, severity='WARNING', message_ru='Проверьте высоту стены: обычно 2–6 м. Пример: 2.7 м.', message_sv='Vägg-/takhöjd brukar vara 2–6 m.'),
            dict(is_active=True, entity='ROOM', field='wall_height_m', rule_type='MIN_MAX', min_value=1.50, max_value=8.00, severity='BLOCK', message_ru='Критично: высота стены вне реалистичного диапазона 1.5–8 м. Исправьте, например на 2.5–3 м.', message_sv='Kritiskt: höjd utanför 1,5–8 m.'),
            dict(is_active=True, entity='ROOM', field='floor_area_m2', rule_type='MIN_MAX', min_value=1.00, max_value=300.00, severity='WARNING', message_ru='Площадь комнаты обычно 1–300 м². Проверьте ввод.', message_sv='Rumsyta brukar vara 1–300 m².'),
            dict(is_active=True, entity='ROOM', field='floor_area_m2', rule_type='MIN_MAX', min_value=0.10, max_value=500.00, severity='BLOCK', message_ru='Критично: площадь должна быть больше 0 и не выглядеть ошибкой (>500 м²).', message_sv='Kritiskt: yta måste vara >0 och rimlig (<=500 m²).'),
            dict(is_active=True, entity='ROOM', field='wall_area_m2_to_floor_area_m2', rule_type='RATIO_MAX', min_value=None, max_value=6.00, severity='WARNING', message_ru='Площадь стен слишком велика относительно пола (обычно не более x6).', message_sv='Väggyta är hög i förhållande till golvyta (ofta max x6).'),
            dict(is_active=True, entity='ROOM', field='wall_area_m2_to_floor_area_m2', rule_type='RATIO_MAX', min_value=None, max_value=10.00, severity='BLOCK', message_ru='Критично: площадь стен выглядит ошибочной (более x10 от пола).', message_sv='Kritiskt: väggyta verkar fel (>x10 av golvyta).'),
            dict(is_active=True, entity='ROOM', field='ceiling_area_m2_to_floor_area_m2', rule_type='DELTA_MAX', min_value=None, max_value=30.00, severity='WARNING', message_ru='Площадь потолка сильно отличается от пола (>30 м²). Проверьте числа.', message_sv='Takytan avviker mycket från golvytan (>30 m²).'),
            dict(is_active=True, entity='ROOM', field='ceiling_area_m2_to_floor_area_m2', rule_type='DELTA_MAX', min_value=None, max_value=80.00, severity='BLOCK', message_ru='Критично: потолок и пол отличаются слишком сильно (>80 м²).', message_sv='Kritiskt: stor avvikelse mellan tak och golv (>80 m²).'),
            dict(is_active=True, entity='ROOM', field='baseboard_length_m', rule_type='MIN_MAX', min_value=0.00, max_value=200.00, severity='WARNING', message_ru='Плинтус >200 м для одной комнаты встречается редко. Проверьте.', message_sv='Sockellängd >200 m är ovanligt för ett rum.'),
            dict(is_active=True, entity='ROOM', field='baseboard_length_m', rule_type='MIN_MAX', min_value=0.00, max_value=500.00, severity='BLOCK', message_ru='Критично: длина плинтуса слишком большая (>500 м).', message_sv='Kritiskt: sockellängd är för stor (>500 m).'),
            dict(is_active=True, entity='WORK_ITEM', field='quantity', rule_type='MIN_MAX', min_value=0.01, max_value=10000.00, severity='BLOCK', message_ru='Количество должно быть больше нуля.', message_sv='Antal måste vara större än noll.'),
            dict(is_active=True, entity='WORK_ITEM', field='quantity', rule_type='MIN_MAX', min_value=0.01, max_value=2000.00, severity='WARNING', message_ru='Очень большое количество, проверьте единицы измерения.', message_sv='Mycket stort antal, kontrollera enhet.'),
            dict(is_active=True, entity='WORK_ITEM', field='difficulty_factor', rule_type='MIN_MAX', min_value=0.50, max_value=3.00, severity='WARNING', message_ru='Коэффициент сложности обычно 0.5–3.0.', message_sv='Svårighetsfaktor brukar vara 0,5–3,0.'),
            dict(is_active=True, entity='WORK_ITEM', field='difficulty_factor', rule_type='MIN_MAX', min_value=0.10, max_value=6.00, severity='BLOCK', message_ru='Критично: коэффициент сложности вне допустимого диапазона.', message_sv='Kritiskt: svårighetsfaktor utanför tillåtet intervall.'),
            dict(is_active=True, entity='PROJECT', field='rooms_count', rule_type='MIN_MAX', min_value=0.00, max_value=150.00, severity='WARNING', message_ru='Слишком много комнат в проекте. Проверьте структуру.', message_sv='Mycket många rum i projektet.'),
            dict(is_active=True, entity='PROJECT', field='work_items_count', rule_type='MIN_MAX', min_value=0.00, max_value=1000.00, severity='WARNING', message_ru='Очень много работ. Возможно, дублирование позиций.', message_sv='Väldigt många arbetsposter.'),
            dict(is_active=True, entity='PROJECT', field='work_items_count', rule_type='MIN_MAX', min_value=0.00, max_value=5000.00, severity='BLOCK', message_ru='Критично: число работ выглядит ошибочным (>5000).', message_sv='Kritiskt: antal arbetsposter verkar fel (>5000).'),
            dict(is_active=True, entity='PROJECT', field='hourly_rate_company', rule_type='MIN_MAX', min_value=100.00, max_value=2000.00, severity='WARNING', message_ru='Ставка компании обычно 100–2000 SEK/ч.', message_sv='Timpris brukar vara 100–2000 SEK/h.'),
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_sanity_rules_id'), table_name='sanity_rules')
    op.drop_table('sanity_rules')
