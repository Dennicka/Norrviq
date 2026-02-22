# CSV Import/Export

## Export endpoints

- `GET /projects/{id}/rooms/export.csv`
- `GET /projects/{id}/work-items/export.csv`

Encoding: UTF-8, delimiter: `,`, decimal separator: `.`.

## Rooms CSV columns (v1)

1. `room_id`
2. `name`
3. `floor_area_m2`
4. `perimeter_m`
5. `ceiling_height_m`
6. `notes`

Example:

```csv
room_id,name,floor_area_m2,perimeter_m,ceiling_height_m,notes
1,Kitchen,10.5,14.2,2.7,Updated
,New room,8.0,11.0,2.6,Created by import
```

## Work Items CSV columns (v1)

1. `item_id`
2. `room_id`
3. `room_name`
4. `work_type_code`
5. `work_type_name`
6. `quantity`
7. `unit`
8. `notes`

Example:

```csv
item_id,room_id,room_name,work_type_code,work_type_name,quantity,unit,notes
12,1,Kitchen,PAINT_WALLS,Paint walls,20,m2,Update qty
,,Bathroom,TILE_FLOOR,Tile floor,6,m2,Create new item
```

## Import workflow

1. Upload file to preview endpoint.
2. Review JSON preview (`created`, `updated`, `issues`, `block_count`).
3. Apply by posting `preview_token` to `POST /projects/{id}/import/apply`.

## Typical errors

- `name is required` — room name must be non-empty.
- `floor_area_m2 must be greater than 0`.
- `Room not found by room_id/room_name`.
- `Work type not found by code/name`.
- `Duplicate room_id in file`.
- `Duplicate room name for create`.
- `File too large (max 5 MB)`.
