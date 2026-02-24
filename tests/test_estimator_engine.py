from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimator_engine import build_project_estimate
from app.services.pricing import get_or_create_project_pricing


def _make_worktype(db, code: str, unit: str, hours_per_unit: Decimal, name_ru: str) -> WorkType:
    wt = WorkType(
        code=f"{code}_{uuid4().hex[:6]}",
        category="paint",
        unit=unit,
        name_ru=name_ru,
        name_sv=name_ru,
        hours_per_unit=hours_per_unit,
        base_difficulty_factor=Decimal("1.00"),
        is_active=True,
    )
    db.add(wt)
    db.flush()
    return wt


def _seed_project(with_missing_wall_dims: bool = False) -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"Estimator {uuid4().hex[:6]}")
        db.add(p)
        db.flush()

        room1 = Room(project_id=p.id, name="R1", floor_area_m2=Decimal("20"), wall_perimeter_m=Decimal("18"), wall_height_m=Decimal("2.5"))
        room2 = Room(project_id=p.id, name="R2", floor_area_m2=Decimal("10"), wall_perimeter_m=None if with_missing_wall_dims else Decimal("14"), wall_height_m=None if with_missing_wall_dims else Decimal("2.5"))
        db.add_all([room1, room2])
        db.flush()

        wt_wall = _make_worktype(db, "wall_paint", "m2", Decimal("0.10"), "Покраска стен")
        wt_ceiling = _make_worktype(db, "ceiling_paint", "m2", Decimal("0.05"), "Покраска потолка")
        wt_room = _make_worktype(db, "cleanup", "room", Decimal("1.00"), "Уборка")

        db.add_all(
            [
                ProjectWorkItem(project_id=p.id, room_id=room1.id, work_type_id=wt_wall.id, quantity=Decimal("1"), calculated_hours=Decimal("4")),
                ProjectWorkItem(project_id=p.id, room_id=room2.id, work_type_id=wt_ceiling.id, quantity=Decimal("1"), calculated_hours=Decimal("2")),
                ProjectWorkItem(project_id=p.id, room_id=None, work_type_id=wt_room.id, quantity=Decimal("1"), calculated_hours=Decimal("1.5")),
            ]
        )

        pricing = get_or_create_project_pricing(db, p.id)
        pricing.hourly_rate_override = Decimal("500")
        pricing.rate_per_m2 = Decimal("200")
        pricing.rate_per_room = Decimal("3000")
        pricing.rate_per_piece = Decimal("1000")
        pricing.fixed_total_price = Decimal("25000")

        db.add(pricing)
        db.commit()
        return p.id
    finally:
        db.close()


def test_base_case_volumes_and_hours():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        estimate = build_project_estimate(db, project_id)
    finally:
        db.close()

    assert estimate["scopes"]["room_count"] == 2
    assert estimate["scopes"]["floor_area_total"] == Decimal("30.0000")
    assert estimate["totals"]["total_hours"] == Decimal("7.5000")
    assert len(estimate["lines"]) == 3


def test_apartment_totals_sum_without_duplicates():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        estimate = build_project_estimate(db, project_id)
    finally:
        db.close()
    summed = sum((line["estimated_hours"] for line in estimate["lines"]), Decimal("0"))
    assert estimate["totals"]["total_hours"] == summed


def test_all_five_pricing_scenarios_present():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        estimate = build_project_estimate(db, project_id)
    finally:
        db.close()
    assert set(estimate["pricing_scenarios"].keys()) == {"hourly", "per_sqm", "per_room", "piecework", "fixed_price"}


def test_missing_data_disables_per_sqm_with_reason():
    project_id = _seed_project(with_missing_wall_dims=True)
    db = SessionLocal()
    try:
        estimate = build_project_estimate(db, project_id)
    finally:
        db.close()
    assert estimate["pricing_scenarios"]["per_sqm"]["enabled"] is False
    assert estimate["pricing_scenarios"]["per_sqm"]["missing_requirements"]


def test_total_hours_equals_sum_of_lines():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        estimate = build_project_estimate(db, project_id)
    finally:
        db.close()

    sum_hours = sum((line["estimated_hours"] for line in estimate["lines"]), Decimal("0"))
    assert estimate["totals"]["total_hours"] == sum_hours
