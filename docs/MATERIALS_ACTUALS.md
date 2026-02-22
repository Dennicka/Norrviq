# Materials Actuals

## How to enter purchases
1. Open `Project -> Materials actuals`.
2. Use **Add Purchase** and fill supplier/date/invoice reference.
3. Add line items (material, packs, pack size, price ex VAT) and save.

## Quick add from shopping list
1. In **Quick add from Shopping List**, select purchased materials.
2. Adjust packs and actual price if needed.
3. Submit to create one purchase batch.
4. Double-click safety is enabled via idempotency key hash.

## Plan vs Actual interpretation
- `planned_*` comes from BOM + Shopping List.
- `actual_*` comes from recorded purchases.
- `delta` = actual - planned.
- `status`:
  - `OK` = equal
  - `UNDER` = purchased less than planned
  - `OVER` = purchased more than planned

Warnings include:
- purchases without price
- purchased materials missing in BOM
- BOM materials not purchased yet

## Baseline integration
In Materials plan settings, enable **Use actual material costs in baseline** (`use_actual_material_costs`) to make pricing baseline consume project material actuals instead of BOM planned costs.
