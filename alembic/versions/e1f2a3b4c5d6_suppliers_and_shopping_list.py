"""suppliers and shopping list support

Revision ID: e1f2a3b4c5d6
Revises: 8a1b2c3d4e5f
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = '8a1b2c3d4e5f'
branch_labels = None
depends_on = None


rounding_enum = sa.Enum('CEIL_TO_PACKS', 'NONE', name='procurement_rounding_mode')


def upgrade() -> None:
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('website', sa.String(length=500), nullable=True),
        sa.Column('phone', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_suppliers_id'), 'suppliers', ['id'], unique=False)

    op.create_table(
        'supplier_material_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.Column('pack_size', sa.Numeric(12, 2), nullable=False),
        sa.Column('pack_unit', sa.String(length=20), nullable=False),
        sa.Column('pack_price_ex_vat', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='SEK'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('supplier_id', 'material_id', 'pack_size', name='uq_supplier_material_pack'),
    )
    op.create_index(op.f('ix_supplier_material_prices_id'), 'supplier_material_prices', ['id'], unique=False)
    op.create_index(op.f('ix_supplier_material_prices_material_id'), 'supplier_material_prices', ['material_id'], unique=False)
    op.create_index(op.f('ix_supplier_material_prices_supplier_id'), 'supplier_material_prices', ['supplier_id'], unique=False)

    rounding_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        'project_procurement_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('preferred_supplier_id', sa.Integer(), nullable=True),
        sa.Column('allow_substitutions', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('auto_select_cheapest', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('rounding_mode', rounding_enum, nullable=False, server_default='CEIL_TO_PACKS'),
        sa.ForeignKeyConstraint(['preferred_supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id'),
    )
    op.create_index(op.f('ix_project_procurement_settings_id'), 'project_procurement_settings', ['id'], unique=False)

    op.add_column('project_cost_items', sa.Column('source_type', sa.String(length=50), nullable=True))
    op.add_column('project_cost_items', sa.Column('source_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_project_cost_items_source_hash'), 'project_cost_items', ['source_hash'], unique=False)

    op.add_column('invoice_lines', sa.Column('source_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_invoice_lines_source_hash'), 'invoice_lines', ['source_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_invoice_lines_source_hash'), table_name='invoice_lines')
    op.drop_column('invoice_lines', 'source_hash')
    op.drop_index(op.f('ix_project_cost_items_source_hash'), table_name='project_cost_items')
    op.drop_column('project_cost_items', 'source_hash')
    op.drop_column('project_cost_items', 'source_type')

    op.drop_index(op.f('ix_project_procurement_settings_id'), table_name='project_procurement_settings')
    op.drop_table('project_procurement_settings')
    rounding_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f('ix_supplier_material_prices_supplier_id'), table_name='supplier_material_prices')
    op.drop_index(op.f('ix_supplier_material_prices_material_id'), table_name='supplier_material_prices')
    op.drop_index(op.f('ix_supplier_material_prices_id'), table_name='supplier_material_prices')
    op.drop_table('supplier_material_prices')

    op.drop_index(op.f('ix_suppliers_id'), table_name='suppliers')
    op.drop_table('suppliers')
