from decimal import Decimal

from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.project_estimator import (
    aggregate_geometry,
    build_project_estimate_summary,
    build_scope,
    calculate_labour_totals,
)


def _room(room_id: int, name: str, floor: str, perimeter: str, height: str) -> Room:
    return Room(id=room_id, name=name, floor_area_m2=Decimal(floor), wall_perimeter_m=Decimal(perimeter), wall_height_m=Decimal(height))


def _item(room_id: int | None, category: str, hours: str, scope_mode: str = "room") -> ProjectWorkItem:
    wt = WorkType(code=f"WT{room_id}{category}", category=category, unit="m2", name_ru="x", name_sv="x", hours_per_unit=Decimal("1"))
    return ProjectWorkItem(room_id=room_id, scope_mode=scope_mode, calculated_hours=Decimal(hours), work_type=wt)


def test_aggregate_two_rooms_sums_geometry():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5"), _room(2, "B", "20", "18", "2.5")]

    scope = build_scope(project, room_ids=[1, 2], all_rooms=False)
    totals = aggregate_geometry(scope)

    assert totals.floors_m2 == Decimal("30.00")
    assert totals.ceilings_m2 == Decimal("30.00")
    assert totals.walls_m2 == Decimal("80.00")


def test_aggregate_all_rooms_in_scope():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5"), _room(2, "B", "20", "18", "2.5"), _room(3, "C", "5", "10", "2.5")]

    scope = build_scope(project, room_ids=None, all_rooms=True)

    assert scope.all_rooms_selected is True
    assert scope.room_ids == {1, 2, 3}


def test_labour_totals_sum_hours():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5")]
    operations = [_item(1, "prep", "2.5"), _item(1, "paint", "3.5")]
    scope = build_scope(project, room_ids=[1], all_rooms=False)

    labour = calculate_labour_totals(scope, operations, Decimal("500"))

    assert labour.total_hours == Decimal("6.00")
    assert labour.by_category["prep"] == Decimal("2.50")
    assert labour.by_category["paint"] == Decimal("3.50")


def test_pricing_modes_hourly_sqm_fixed():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5")]
    project.work_items = [_item(1, "paint", "4")]

    summary_hourly = build_project_estimate_summary(
        project=project,
        room_ids=[1],
        pricing_mode="hourly",
        hourly_rate=Decimal("400"),
        sqm_rate=Decimal("200"),
        fixed_price=Decimal("7000"),
    )
    summary_sqm = build_project_estimate_summary(
        project=project,
        room_ids=[1],
        pricing_mode="sqm",
        hourly_rate=Decimal("400"),
        sqm_rate=Decimal("200"),
        fixed_price=Decimal("7000"),
    )
    summary_fixed = build_project_estimate_summary(
        project=project,
        room_ids=[1],
        pricing_mode="fixed",
        hourly_rate=Decimal("400"),
        sqm_rate=Decimal("200"),
        fixed_price=Decimal("7000"),
    )

    assert summary_hourly.total_price == Decimal("1600.00")
    assert summary_sqm.total_price == Decimal("7000.00")
    assert summary_fixed.total_price == Decimal("7000.00")
    assert summary_fixed.labour.total_hours == Decimal("4.00")


def test_calculate_work_item_totals_hourly():
    project = Project(name="P")
    room = _room(1, "A", "10", "14", "2.5")
    project.rooms = [room]
    scope = build_scope(project, room_ids=[1], all_rooms=False)
    item = ProjectWorkItem(id=1, room_id=1, pricing_mode="hourly", calculated_hours=Decimal("3"), hourly_rate_sek=Decimal("500"))

    from app.services.project_estimator import calculate_work_item_totals

    line = calculate_work_item_totals(item=item, scope=scope)
    assert line.line_total == Decimal("1500.00")
    assert line.labour_hours == Decimal("3.00")


def test_calculate_work_item_totals_sqm():
    project = Project(name="P")
    room = _room(1, "A", "10", "14", "2.5")
    project.rooms = [room]
    scope = build_scope(project, room_ids=[1], all_rooms=False)
    item = ProjectWorkItem(id=1, room_id=1, pricing_mode="sqm", billable_area_m2=Decimal("35"), area_rate_sek=Decimal("200"))

    from app.services.project_estimator import calculate_work_item_totals

    line = calculate_work_item_totals(item=item, scope=scope)
    assert line.line_total == Decimal("7000.00")
    assert line.calculated_quantity == Decimal("35.00")


def test_calculate_work_item_totals_fixed():
    project = Project(name="P")
    room = _room(1, "A", "10", "14", "2.5")
    project.rooms = [room]
    scope = build_scope(project, room_ids=[1], all_rooms=False)
    item = ProjectWorkItem(id=1, room_id=1, pricing_mode="fixed", fixed_price_sek=Decimal("7200"), calculated_hours=Decimal("4"))

    from app.services.project_estimator import calculate_work_item_totals

    line = calculate_work_item_totals(item=item, scope=scope)
    assert line.line_total == Decimal("7200.00")
    assert line.labour_hours == Decimal("4.00")


def test_calculate_project_totals_mixed_modes():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5")]
    scope = build_scope(project, room_ids=[1], all_rooms=False)
    items = [
        ProjectWorkItem(id=1, room_id=1, pricing_mode="hourly", calculated_hours=Decimal("2"), hourly_rate_sek=Decimal("500")),
        ProjectWorkItem(id=2, room_id=1, pricing_mode="sqm", billable_area_m2=Decimal("10"), area_rate_sek=Decimal("200"), calculated_hours=Decimal("1")),
        ProjectWorkItem(id=3, room_id=1, pricing_mode="fixed", fixed_price_sek=Decimal("3000"), calculated_hours=Decimal("0.5")),
    ]

    from app.services.project_estimator import calculate_project_totals

    totals = calculate_project_totals(scope=scope, work_items=items, vat_rate_percent=Decimal("25"))
    assert totals.total_labour_hours == Decimal("3.50")
    assert totals.subtotal == Decimal("6000.00")
    assert totals.vat_amount == Decimal("1500.00")
    assert totals.total_inc_vat == Decimal("7500.00")


def test_project_scope_item_hours_are_included_for_all_rooms_scope():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5"), _room(2, "B", "20", "18", "2.5")]
    scope = build_scope(project, room_ids=None, all_rooms=True)
    operations = [
        _item(None, "paint", "5", scope_mode="project"),
        _item(1, "prep", "2", scope_mode="room"),
    ]

    labour = calculate_labour_totals(scope, operations, Decimal("500"))

    assert labour.total_hours == Decimal("7.00")
    assert labour.by_category["paint"] == Decimal("5.00")


def test_project_scope_item_excluded_from_single_room_scope():
    project = Project(name="P")
    project.rooms = [_room(1, "A", "10", "14", "2.5"), _room(2, "B", "20", "18", "2.5")]
    scope = build_scope(project, room_ids=[1], all_rooms=False)
    operations = [_item(None, "paint", "5", scope_mode="project")]

    labour = calculate_labour_totals(scope, operations, Decimal("500"))

    assert labour.total_hours == Decimal("0.00")
