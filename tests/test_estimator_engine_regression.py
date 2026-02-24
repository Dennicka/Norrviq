from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimator_engine import build_project_estimate
from app.services.pricing import get_or_create_project_pricing


def test_estimator_engine_golden_case():
    db = SessionLocal()
    try:
        project = Project(name=f"Golden {uuid4().hex[:6]}")
        db.add(project)
        db.flush()
        room = Room(project_id=project.id, name="Studio", floor_area_m2=Decimal("25"), wall_perimeter_m=Decimal("20"), wall_height_m=Decimal("2.6"))
        db.add(room)
        db.flush()

        wt = WorkType(
            code=f"golden_wall_{uuid4().hex[:6]}",
            category="paint",
            unit="m2",
            name_ru="Покраска стен",
            name_sv="Покраска стен",
            hours_per_unit=Decimal("0.20"),
            base_difficulty_factor=Decimal("1"),
            is_active=True,
        )
        db.add(wt)
        db.flush()

        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("2"), calculated_hours=Decimal("10"), materials_cost_sek=Decimal("1500")))

        pricing = get_or_create_project_pricing(db, project.id)
        pricing.hourly_rate_override = Decimal("400")
        pricing.fixed_total_price = Decimal("8000")
        pricing.rate_per_m2 = Decimal("250")
        pricing.rate_per_room = Decimal("3000")
        pricing.rate_per_piece = Decimal("1000")
        db.add(pricing)
        db.commit()

        result = build_project_estimate(db, project.id)
    finally:
        db.close()

    assert result["totals"]["total_hours"] == Decimal("10.0000")
    assert result["totals"]["total_cost"] == Decimal("5500.00")
    assert result["pricing_scenarios"]["fixed_price"]["gross_profit"] == Decimal("2500.00")
