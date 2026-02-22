# Bulk operations for Rooms/Zones

## 70 rooms in ~2 minutes

1. Open `/projects/{id}/rooms`.
2. In **Bulk actions → Create rooms from template** fill:
   - `Name template`: `Room {i}` (or `Bedroom {i}`, `Office-{i}`)
   - `N`: required count (1..200)
   - Optional shared dimensions (`height`, `floor area`, `perimeter`, `ceiling area`).
3. Check preview table (first 5 names + total count).
4. Press **Create**.

## Fast duplication

- **Duplicate** on any room creates one full copy with all geometry and description.
- **Create copies…** creates N copies (1..200) from one source room.
- You can provide prefix for automatic numbering (`Bedroom 1`, `Bedroom 2`, ...).

## Batch edit selected rooms

1. Select rooms via checkboxes in the rooms list.
2. Use **Edit selected** form.
3. Set fields to apply (`Height`, `Description/tag`).
4. Optional: enable **Apply only if empty** to avoid overwriting existing values.
5. Confirm summary before save.

## Naming template examples

- `Room {i}` → `Room 1`, `Room 2`, ...
- `Bedroom-{i}` → `Bedroom-1`, `Bedroom-2`, ...
- `Apt 45 / Zone {i}` → `Apt 45 / Zone 1`, ...
