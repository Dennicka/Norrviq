from dataclasses import asdict
from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimates import calculate_work_item
from app.services.pricing import compute_pricing_scenarios, get_or_create_project_pricing

EXPECTED_MODE_ORDER = ["HOURLY", "PER_M2", "FIXED_TOTAL", "PER_ROOM", "PIECEWORK"]


def _make_stable_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Determinism {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)

        wt = WorkType(
            code=f"DET-{uuid4().hex[:6]}",
            category="paint",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.50"),
            base_difficulty_factor=Decimal("1.00"),
            is_active=True,
        )
        db.add(wt)
        db.flush()

        room1 = Room(project_id=project.id, name="R1", wall_area_m2=Decimal("12.00"), ceiling_area_m2=Decimal("10.00"), floor_area_m2=Decimal("10.00"))
        room2 = Room(project_id=project.id, name="R2", wall_area_m2=Decimal("18.00"), ceiling_area_m2=Decimal("14.00"), floor_area_m2=Decimal("14.00"))
        db.add_all([room1, room2])
        db.flush()

        item1 = ProjectWorkItem(project_id=project.id, room_id=room1.id, work_type_id=wt.id, quantity=Decimal("5.00"), difficulty_factor=Decimal("1.00"))
        item2 = ProjectWorkItem(project_id=project.id, room_id=room2.id, work_type_id=wt.id, quantity=Decimal("7.00"), difficulty_factor=Decimal("1.00"))
        calculate_work_item(item1, wt, Decimal("500.00"))
        calculate_work_item(item2, wt, Decimal("500.00"))
        db.add_all([item1, item2])
        db.commit()

        pricing = get_or_create_project_pricing(db, project.id)
        pricing.hourly_rate_override = Decimal("620.00")
        pricing.rate_per_m2 = Decimal("240.00")
        pricing.fixed_total_price = Decimal("15000.00")
        pricing.rate_per_room = Decimal("4200.00")
        pricing.rate_per_piece = Decimal("1800.00")
        db.commit()
        return project.id
    finally:
        db.close()


def test_compute_pricing_scenarios_is_deterministic_and_stable_order():
    project_id = _make_stable_project()

    db = SessionLocal()
    try:
        baseline1, scenarios1 = compute_pricing_scenarios(db, project_id)
        baseline2, scenarios2 = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()

    assert asdict(baseline1) == asdict(baseline2)
    assert [scenario.mode for scenario in scenarios1] == EXPECTED_MODE_ORDER
    assert [scenario.mode for scenario in scenarios2] == EXPECTED_MODE_ORDER
    assert [asdict(scenario) for scenario in scenarios1] == [asdict(scenario) for scenario in scenarios2]
