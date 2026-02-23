from decimal import Decimal

from app.models.room import Room
from app.services.geometry import GeometryValidationError, compute_room_geometry_from_model


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
    """Recalculate derived fields without crashing on incomplete room geometry."""

    try:
        result = compute_room_geometry_from_model(room)
    except GeometryValidationError:
        room.wall_area_m2 = None
        room.ceiling_area_m2 = None
        room.baseboard_length_m = None
        return

    room.wall_perimeter_m = result.perimeter_m if result.perimeter_m is not None else _to_decimal(room.wall_perimeter_m)
    room.floor_area_m2 = result.floor_area_m2 if result.floor_area_m2 is not None else _to_decimal(room.floor_area_m2)
    room.wall_area_m2 = result.wall_area_net_m2
    room.ceiling_area_m2 = result.ceiling_area_m2
    room.baseboard_length_m = result.baseboard_lm
