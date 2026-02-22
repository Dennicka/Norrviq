# Invoice Materials v2

`POST /projects/{project_id}/invoices/{invoice_id}/add-material-lines` генерирует itemized строки материалов из `SHOPPING_LIST` (по умолчанию) или `BOM`.

## Pricing policy

Настройки хранятся в `project_procurement_settings`:
- `material_pricing_mode`: `SELL_PRICE` или `COST_PLUS_MARKUP`.
- `material_markup_pct`: маркап для `COST_PLUS_MARKUP` (default `20%`).
- `round_invoice_materials_to_packs`: округление BOM в пачки.
- `invoice_material_unit`: `PACKS` или `BASE_UNIT`.

## Line generation

Каждая строка материалов создается как:
- `kind=MATERIAL`
- `source_type=SHOPPING_LIST|BOM`
- `source_id=material_id`
- `description=name + sku + pack_size (для PACKS)`

`PACKS`:
- `qty=packs_count`
- `unit=pack`
- `unit_price_ex_vat=pack_price` (или `pack_cost*(1+markup%)`)

`BASE_UNIT`:
- `qty=qty_final_unit`
- `unit=material.unit`
- `unit_price_ex_vat=pack_price/pack_size` (или cost-plus).

## Pricing consistency

Finalize invoice блокируется, если есть `MATERIAL` lines и `project_pricing.include_materials=false`.

## Snapshots

На issue дополнительно используется snapshot-поле инвойса:
- `material_pricing_snapshot`
- `material_source_snapshot_hash`

Это фиксирует applied pricing/source на момент выдачи документа.
