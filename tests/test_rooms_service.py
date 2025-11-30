from decimal import Decimal

from app.services.rooms import recalc_room_dimensions
from app.models.room import Room


def test_recalc_room_dimensions_full():
    room = Room(wall_perimeter_m=Decimal("12.5"), wall_height_m=Decimal("2.40"), floor_area_m2=Decimal("20.0"))

    recalc_room_dimensions(room)

    assert room.wall_area_m2 == Decimal("30.00")
    assert room.ceiling_area_m2 == Decimal("20.0")
    assert room.baseboard_length_m == Decimal("12.5")


def test_recalc_room_dimensions_partial():
    room = Room(wall_perimeter_m=None, wall_height_m=Decimal("3.0"), floor_area_m2=None)

    recalc_room_dimensions(room)

    assert room.wall_area_m2 is None
    assert room.ceiling_area_m2 is None
    assert room.baseboard_length_m is None
