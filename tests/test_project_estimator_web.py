from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.pricing import get_or_create_project_pricing


client = TestClient(app)
settings = get_settings()


def login():
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def test_project_estimator_page_and_mode_switch_affects_offer():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Estimator Web")
        room = Room(name="Kitchen", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("14"), wall_height_m=Decimal("2.5"))
        wt = WorkType(code="PAINT_WEB", category="paint", unit="m2", name_ru="Покраска", name_sv="Målning", hours_per_unit=Decimal("1"))
        item = ProjectWorkItem(
            quantity=Decimal("10"),
            difficulty_factor=Decimal("1"),
            calculated_hours=Decimal("4"),
            labor_cost_sek=Decimal("1600"),
            materials_cost_sek=Decimal("350"),
            work_type=wt,
            room=room,
        )
        project.rooms.append(room)
        project.work_items.append(item)
        db.add(project)
        db.commit()
        db.refresh(project)
        pricing = get_or_create_project_pricing(db, project.id)
        pricing.fixed_total_price = Decimal("9000")
        pricing.rate_per_m2 = Decimal("300")
        db.add(pricing)
        db.commit()
        project_id = project.id
    finally:
        db.close()

    detail = client.get(f"/projects/{project_id}")
    assert detail.status_code == 200
    assert "Сводка сметы" in detail.text
    assert "Режим ценообразования" in detail.text
    assert "Общие часы" in detail.text
    assert "Работы" in detail.text
    assert "Материалы" in detail.text
    assert "Итого" in detail.text
    assert "По помещениям" in detail.text

    switch = client.post(
        f"/projects/{project_id}/estimator-pricing-mode",
        data={"project_pricing_mode": "fixed", "fixed_price_amount": "9000"},
        follow_redirects=False,
    )
    assert switch.status_code == 303

    offer = client.get(f"/projects/{project_id}/offer")
    assert offer.status_code == 200
    assert "FIXED_TOTAL" in offer.text


def test_project_estimator_warns_for_missing_room_dimensions():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Estimator Missing")
        room = Room(name="NoGeometry", floor_area_m2=Decimal("0"), wall_perimeter_m=None, wall_height_m=None)
        wt = WorkType(code="PAINT_MISS", category="paint", unit="m2", name_ru="Покраска", name_sv="Målning", hours_per_unit=Decimal("1"))
        item = ProjectWorkItem(
            quantity=Decimal("2"),
            difficulty_factor=Decimal("1"),
            calculated_hours=Decimal("2"),
            labor_cost_sek=Decimal("800"),
            work_type=wt,
            room=room,
        )
        project.rooms.append(room)
        project.work_items.append(item)
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    detail = client.get(f"/projects/{project_id}")
    assert detail.status_code == 200
    assert "Не хватает данных для полного расчёта" in detail.text
