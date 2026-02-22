# Paint Systems

Paint System = versioned bundle of recipe steps (primer/coats) with target surfaces.

## Structure
- `paint_systems`: name + version, immutable history by versioning.
- `paint_system_steps`: ordered steps linked to `material_recipes`, with optional coats/waste overrides.
- Assignment levels:
  - project defaults (`project_paint_settings`): wall + ceiling systems.
  - room overrides (`room_paint_settings`): room-specific wall + ceiling systems.

## Versioning
- Existing version should not be edited after use.
- Use **Create new version** to clone steps and increment `version`.
- Previous version is marked inactive/read-only.

## BOM behavior
- If paint systems are assigned, BOM is calculated room-by-room from room areas:
  - `WALLS` -> room wall area (`perimeter * height`, stored in room wall area)
  - `CEILING` -> room ceiling area
  - `FLOOR` -> room floor area
  - `PAINTABLE_TOTAL` -> wall + ceiling
- Quantity formula per step: `consumption_per_m2 * area * coats * (1 + waste_pct/100)`.
- Quantities are aggregated by material across all rooms/systems.
- If no paint system is assigned, legacy project/worktype recipes are used as fallback.

## Example systems
- Standard walls: primer on `WALLS` + top coat x2 on `WALLS`.
- Ceiling light: primer on `CEILING` + top coat x1 on `CEILING`.
- Wet room: dedicated moisture-resistant recipes with higher waste.
