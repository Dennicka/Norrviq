# Offer commercial model

`compute_offer_commercial(db, project_id)` is the single source of truth for offer commercial totals.

## Customer-facing line rules

- `HOURLY`: one line `Arbete (löpande räkning)` with hours and hourly rate.
- `FIXED_TOTAL`: one line `Fast pris för målning enligt överenskommelse` (`qty=1`, `unit=st`).
- `PER_M2`: one line with selected takeoff basis and `m²` quantity.
- `PER_ROOM`: one line `Målning per rum` with room count.
- `PIECEWORK`: one line `Arbete enligt styckpris` with items count.

## Snapshot on issue

When offer is issued, project stores `offer_commercial_snapshot` JSON containing:

- selected mode
- units (`m2_basis`, `total_m2`, `rooms_count`, `items_count`)
- rates used
- totals (`price_ex_vat`, `vat_amount`, `price_inc_vat`)
- line items and warnings
- internal `math_breakdown`

Issued offer page/PDF always renders from snapshot (no live recomputation).

## Why fixed mode is not itemized

For fixed offers customer sees only negotiated fixed line, to avoid exposing internal hourly construction and to keep document consistent with selected selling model.
