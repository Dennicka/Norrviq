# Invoice Commercial

`compute_invoice_commercial(db, project_id, invoice_id=None)` is the single source of truth for invoice commercial model.

Includes:
- selected pricing mode
- units (`m2_basis`, `total_m2`, `rooms_count`, `items_count`)
- rates (`hourly_rate_override`, `fixed_total_price`, `rate_per_m2`, `rate_per_room`, `rate_per_piece`)
- `price_ex_vat`, `vat_amount`, `price_inc_vat`
- recommended invoice lines for selected mode
- VAT/ROT breakdown and warnings

Generation uses selected mode:
- `HOURLY`: itemized labour from work items
- `FIXED_TOTAL`: one labour line, qty=1, unit=st
- `PER_M2`: one labour line, qty=`total_m2` by takeoff basis, unit=m²
- `PER_ROOM`: one labour line, qty=`rooms_count`, unit=rum
- `PIECEWORK`: one labour line, qty=`items_count`, unit=st

On issue, invoice stores immutable commercial snapshots (mode/units/rates/totals).
