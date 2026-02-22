# Shopping List

## Setup suppliers and prices
1. Open `/settings/suppliers` (admin only).
2. Create supplier.
3. Add material pack prices per supplier.

## How shopping list is built
- Source: project BOM.
- Price selection:
  - preferred supplier price when available;
  - otherwise cheapest supplier if enabled;
  - otherwise fallback to material default unit cost with warning.
- Pack rounding uses project procurement setting (`CEIL_TO_PACKS` by default).

## Export and apply
- CSV: `/projects/{id}/shopping-list/export.csv`
- PDF: `/projects/{id}/shopping-list/export.pdf`
- Apply to project costs writes `source_type=SHOPPING_LIST` + `source_hash` and is idempotent.
- Apply to draft invoice upserts material lines by `material_id` and writes `source_hash`.
