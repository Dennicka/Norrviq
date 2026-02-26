from decimal import Decimal
from types import SimpleNamespace

from app.services.estimator_engine import ProjectGeometry, RoomGeometry, compute_work_item_qty


def _item(**kwargs):
    base = {
        "scope_mode": "PROJECT",
        "basis_type": "floor_area_m2",
        "room_id": None,
        "selected_room_ids_json": None,
        "manual_qty": None,
        "quantity": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_project_scope_sums_all_room_floor_areas():
    rooms = {1: RoomGeometry(room_id=1, floor_area_m2=Decimal("10")), 2: RoomGeometry(room_id=2, floor_area_m2=Decimal("15"))}
    qty = compute_work_item_qty(_item(scope_mode="PROJECT"), rooms, ProjectGeometry(rooms=rooms))
    assert qty == Decimal("25.00")


def test_selected_rooms_sums_only_selected_rooms():
    rooms = {1: RoomGeometry(room_id=1, floor_area_m2=Decimal("10")), 2: RoomGeometry(room_id=2, floor_area_m2=Decimal("15"))}
    qty = compute_work_item_qty(_item(scope_mode="SELECTED_ROOMS", selected_room_ids_json="[2]"), rooms, ProjectGeometry(rooms=rooms))
    assert qty == Decimal("15.00")


def test_custom_qty_does_not_overwrite_manual_qty():
    rooms = {1: RoomGeometry(room_id=1, floor_area_m2=Decimal("10"))}
    qty = compute_work_item_qty(_item(scope_mode="CUSTOM_QTY", manual_qty=Decimal("7.25")), rooms, ProjectGeometry(rooms=rooms))
    assert qty == Decimal("7.25")
