# Offer commercial model

`compute_offer_commercial(db, project_id)` builds both client-facing and internal commercial structures from pricing/takeoff/material inputs.

## Single source of truth

- Builder: `app/services/offer_commercial.py`.
- Totals engine: `app/services/offer_totals.py` via `compute_offer_totals(...)`.
- Templates render prepared sections/summary and never recompute business totals inline.

## Commercial structure

Commercial payload includes:

- `sections[]` (ordered groups with line items).
- line item fields: `source_ref`, `description`, `qty`, `unit`, `unit_price`, `total`, `category`, `split`, `visible`.
- `summary`: `labour_subtotal`, `materials_subtotal`, `other_subtotal`, `discount`, `subtotal_ex_vat`, `vat_amount`, `total_inc_vat`, `rot_ready_base`.
- `math_breakdown`: internal-only profitability inputs (hours/costs/buffers/profile).
- `metadata.project_marker`: hash used for stale snapshot detection.

## Rounding policy (SEK)

`compute_offer_totals` applies:

1. component rounding to öre (`0.01`, HALF_UP),
2. discounts on ex-VAT subtotal,
3. VAT on discounted subtotal,
4. final total rounding.

## Internal vs client view

`/projects/{id}/offer?view=client|internal`:

- client view: sections + clean totals + terms.
- internal view: technical breakdown (hours/cost basis/buffers/speed profile).

## Snapshot consistency

- Issued offer keeps immutable commercial snapshot.
- Staleness warning compares snapshot marker vs current project marker.
