from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.project_pricing import ProjectPricing
from app.models.room import Room
from app.models.settings import Settings
from app.models.worktype import WorkType
from app.services.estimator_engine import calculate_project_pricing_totals


def _seed() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Estimator Pricing {uuid4().hex[:6]}")
        room = Room(project=project, name="A", floor_area_m2=Decimal("20"), wall_area_m2=Decimal("40"), ceiling_area_m2=Decimal("20"), wall_perimeter_m=Decimal("18"))
        wt = WorkType(code=f"WT-{uuid4().hex[:5]}", name_ru="Тест", name_sv="Test", category="paint", unit="m2", hours_per_unit=Decimal("0.5"), is_active=True)
        item = ProjectWorkItem(
            project=project,
            room=room,
            work_type=wt,
            scope_mode="ROOM",
            basis_type="floor_area_m2",
            pricing_mode="HOURLY",
            hourly_rate_ex_vat=Decimal("600"),
            unit_rate_ex_vat=Decimal("200"),
            fixed_total_ex_vat=Decimal("5000"),
            norm_hours_per_unit=Decimal("0.5"),
            quantity=Decimal("1"),
            difficulty_factor=Decimal("1"),
        )
        pricing = ProjectPricing(project=project, mode="HOURLY")
        db.add_all([project, room, wt, item, pricing])
        settings = db.query(Settings).first()
        if settings:
            settings.internal_labor_cost_rate_sek = Decimal("250")
            settings.moms_percent = Decimal("25")
        db.commit()
        return project.id
    finally:
        db.close()


def test_hourly_and_per_m2_totals_differ_and_effective_hourly():
    pid = _seed()
    db = SessionLocal()
    try:
        hourly = calculate_project_pricing_totals(db, pid, "HOURLY")
        per_m2 = calculate_project_pricing_totals(db, pid, "PER_M2")
    finally:
        db.close()

    assert hourly.sell_ex_vat != per_m2.sell_ex_vat
    assert hourly.effective_hourly_ex_vat == (hourly.sell_ex_vat / hourly.total_hours).quantize(Decimal("0.01"))


def test_hours_deterministic_with_norm_hours_per_unit():
    pid = _seed()
    db = SessionLocal()
    try:
        first = calculate_project_pricing_totals(db, pid, "HOURLY")
        second = calculate_project_pricing_totals(db, pid, "HOURLY")
    finally:
        db.close()

    assert first.total_hours == second.total_hours == Decimal("10.00")
