# Takeoff Areas (m² basis)

Per-m² pricing now uses explicit **m² basis** configured per project:

- `FLOOR_AREA`
- `WALL_AREA`
- `CEILING_AREA`
- `PAINTABLE_TOTAL` (= `WALL_AREA + CEILING_AREA`)

## Formulas

Per room:

- `floor_area_m2` — from room input.
- `ceiling_area_m2 = floor_area_m2`.
- `wall_area_m2 = perimeter_m * ceiling_height_m`.

Project totals:

- `total_floor_m2 = Σ floor_area_m2`
- `total_ceiling_m2 = Σ ceiling_area_m2`
- `total_wall_m2 = Σ wall_area_m2`
- `total_paintable_m2 = total_wall_m2 + total_ceiling_m2`

All computations use `Decimal`, quantized to 2 decimals.

## Limitations (v1)

- Openings subtraction (windows/doors) is not applied yet.
- Non-uniform wall height by segments is not supported.
