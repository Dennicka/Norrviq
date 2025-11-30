from decimal import Decimal

from app.models.room import Room


def _to_decimal(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def recalc_room_dimensions(room: Room) -> None:
    """Recalculate derived fields (wall_area_m2, ceiling_area_m2, baseboard_length_m)."""

    wall_perimeter = _to_decimal(room.wall_perimeter_m)
    wall_height = _to_decimal(room.wall_height_m)
    floor_area = _to_decimal(room.floor_area_m2)

    room.wall_area_m2 = wall_perimeter * wall_height if wall_perimeter is not None and wall_height is not None else None
    room.ceiling_area_m2 = floor_area if floor_area is not None else None
    room.baseboard_length_m = wall_perimeter if wall_perimeter is not None else None
