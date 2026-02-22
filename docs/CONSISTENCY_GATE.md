# Consistency Gate

`validate_pricing_consistency` is a single entrypoint used during Offer/Invoice issue.

## What is checked

- Selected pricing mode exists on project.
- Pricing scenario exists for selected mode.
- Scenario totals match computed commercial totals (`±0.01 SEK`).
- Units/basis checks:
  - `PER_M2` requires `m2_basis` and `total_m2 > 0`.
  - `PER_ROOM` requires `rooms_count > 0`.
  - `PIECEWORK` requires `items_count > 0`.
- Rates are checked against selected scenario for mode-relevant rate fields.
- Invoice-specific checks:
  - `invoice.subtotal_ex_vat == scenario.price_ex_vat` (`±0.01 SEK`) when invoice has lines.
  - Invoice subtotal matches commercial totals (`±0.01 SEK`).

## Error codes

- `PROJECT_NOT_FOUND`
- `MISSING_SELECTED_MODE`
- `SCENARIO_NOT_FOUND`
- `TOTAL_PRICE_EX_VAT_MISMATCH`
- `INVALID_PER_M2_BASIS`
- `INVALID_PER_ROOM_UNITS`
- `INVALID_PIECEWORK_UNITS`
- `RATE_MISMATCH`
- `INVOICE_NOT_FOUND`
- `INVOICE_SUBTOTAL_MISMATCH`
- `INVOICE_COMMERCIAL_MISMATCH`

## Troubleshooting

Common fix flow:
1. Regenerate invoice lines from project pricing.
2. Recalculate pricing mode/inputs in Pricing page.
3. Check takeoff basis/room metrics and update missing units.
4. Retry issue.

Every failed gate logs `pricing_consistency_failed` audit event with detailed errors payload.
