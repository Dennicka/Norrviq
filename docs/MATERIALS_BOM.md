# Materials BOM

## Materials

Create materials in `/materials` with:
- unit (`L`, `KG`, `PCS`, `ROLL`, `M`, etc.)
- optional `default_pack_size`
- optional `default_cost_per_unit_ex_vat`
- optional `default_sell_per_unit_ex_vat`
- optional `default_markup_pct`

## Recipes

`material_recipes` define consumption norms:
- `basis`: `FLOOR_AREA`, `WALL_AREA`, `CEILING_AREA`, `PAINTABLE_TOTAL`
- `consumption_per_m2`
- `coats_count`
- `waste_pct`
- `rounding_mode`: `NONE` or `CEIL_TO_PACKS`

Formula:

`qty = area_m2 * consumption_per_m2 * coats_count * (1 + waste_pct/100)`

Example: paint `0.10 L/m²`, `2` coats, `8%` waste:
- for `30 m²` wall area:
- `30 * 0.10 * 2 * 1.08 = 6.48 L`
- with pack `10L` and `CEIL_TO_PACKS` => `1` pack => `10.00 L` final.

## Project Materials Plan

Page: `/projects/{id}/materials-plan`
- shows area totals and BOM lines
- supports default markup and sell-price mode
- apply BOM to project cost items
- apply BOM to draft invoice as `MATERIAL` lines

## Pricing Integration

`project_material_settings.include_materials_in_pricing` controls baseline override:
- if enabled and BOM has items, baseline `materials_cost_internal = BOM total cost`
- if disabled, old manual project material costs remain in use.
