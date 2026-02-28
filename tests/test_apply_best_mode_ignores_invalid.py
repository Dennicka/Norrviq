from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.estimates import calculate_work_item
from app.services.pricing import compute_pricing_scenarios, get_or_create_project_pricing

client = TestClient(app)
settings = get_settings()


def _login_admin():
    return client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _create_project_with_invalid_fixed_total() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Apply best {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)

        wt = WorkType(
            code=f"ABM-{uuid4().hex[:6]}",
            category="paint",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("2.00"),
            base_difficulty_factor=Decimal("1.00"),
            is_active=True,
        )
        db.add(wt)
        db.flush()

        room = Room(project_id=project.id, name="Room", floor_area_m2=Decimal("20.00"))
        db.add(room)
        db.flush()

        item = ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("5.00"), difficulty_factor=Decimal("1.00"))
        calculate_work_item(item, wt, Decimal("650.00"))
        db.add(item)
        db.commit()

        pricing = get_or_create_project_pricing(db, project.id)
        pricing.hourly_rate_override = Decimal("700.00")
        pricing.fixed_total_price = Decimal("-100.00")
        pricing.rate_per_m2 = Decimal("200.00")
        pricing.rate_per_room = Decimal("5000.00")
        pricing.rate_per_piece = Decimal("1500.00")
        db.commit()
        return project.id
    finally:
        db.close()


def test_apply_best_mode_ignores_invalid_scenario():
    _login_admin()
    project_id = _create_project_with_invalid_fixed_total()

    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"intent": "apply_best_mode", "best_metric": "profit"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        pricing = get_or_create_project_pricing(db, project_id)
        _, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()

    fixed = next(s for s in scenarios if s.mode == "FIXED_TOTAL")
    assert fixed.is_valid is False
    assert pricing.mode != "FIXED_TOTAL"
    chosen = next(s for s in scenarios if s.mode == pricing.mode)
    assert chosen.is_valid is True
