from decimal import Decimal

from app.models.project import Project
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.geometry import (
    GeometryResult,
    geometry_completeness,
    is_geometry_complete_for_walls,
)
from app.services.work_scope_apply import build_scope_preview


def _work_type(category: str = "wall paint") -> WorkType:
    return WorkType(code="WT-PREVIEW", category=category, name_ru="", name_sv="", hours_per_unit=Decimal("1.0"))


def _project_with_rooms(*rooms: Room) -> Project:
    project = Project(name="Preview Project")
    project.rooms = list(rooms)
    return project


def test_scope_preview_custom_qty_does_not_require_geometry():
    room = Room(id=1, name="R1", floor_area_m2=None, wall_perimeter_m=None, wall_height_m=None)
    preview = build_scope_preview(
        project=_project_with_rooms(room),
        work_type=_work_type(),
        scope_apply_mode="custom_qty",
        manual_qty=Decimal("123"),
    )

    assert preview.estimated_quantity == Decimal("123.00")
    assert not any("INCOMPLETE_GEOMETRY" in warning for warning in preview.warnings)


def test_scope_preview_room_walls_incomplete_geometry_warns():
    room = Room(id=11, name="R11", floor_area_m2=Decimal("12"), wall_perimeter_m=None, wall_height_m=None, wall_area_m2=None)
    preview = build_scope_preview(
        project=_project_with_rooms(room),
        work_type=_work_type("wall paint"),
        scope_apply_mode="single_room",
        room_id=11,
        basis_type="wall_area_m2",
    )

    assert any("INCOMPLETE_GEOMETRY" in warning for warning in preview.warnings)


def test_scope_preview_room_walls_complete_when_wall_area_present():
    room = Room(id=21, name="R21", floor_area_m2=Decimal("10"), wall_perimeter_m=None, wall_height_m=None, wall_area_m2=Decimal("40"))
    preview = build_scope_preview(
        project=_project_with_rooms(room),
        work_type=_work_type("wall paint"),
        scope_apply_mode="single_room",
        room_id=21,
        basis_type="wall_area_m2",
    )

    geom = GeometryResult(wall_area_m2=Decimal("40"))
    assert is_geometry_complete_for_walls(geom) is True
    assert geometry_completeness(geom)["walls"] is True
    assert preview.estimated_quantity == Decimal("40.00")
    assert not any("INCOMPLETE_GEOMETRY" in warning for warning in preview.warnings)


def test_scope_preview_project_aggregates_selected_rooms():
    room1 = Room(id=101, name="R101", floor_area_m2=Decimal("10"), wall_perimeter_m=None, wall_height_m=None, wall_area_m2=Decimal("10"))
    room2 = Room(id=102, name="R102", floor_area_m2=Decimal("10"), wall_perimeter_m=None, wall_height_m=None, wall_area_m2=Decimal("20"))
    room3 = Room(id=103, name="R103", floor_area_m2=Decimal("10"), wall_perimeter_m=None, wall_height_m=None, wall_area_m2=None)

    preview = build_scope_preview(
        project=_project_with_rooms(room1, room2, room3),
        work_type=_work_type("wall paint"),
        scope_apply_mode="selected_rooms",
        room_ids=[101, 102],
        basis_type="wall_area_m2",
    )

    assert preview.estimated_quantity == Decimal("30.00")
    assert not any("INCOMPLETE_GEOMETRY" in warning for warning in preview.warnings)
