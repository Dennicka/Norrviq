from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project
from app.models.room import Room
from app.services.pricing import compute_pricing_scenarios, get_or_create_project_pricing
from app.services.takeoff import compute_project_areas, get_or_create_project_takeoff_settings

client = TestClient(app)
settings = get_settings()


def _login():
    return client.post("/login", data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"}, follow_redirects=False)


def _project_with_room(*, with_dims: bool = True) -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"Takeoff {uuid4().hex[:6]}")
        db.add(p)
        db.flush()
        room = Room(
            project_id=p.id,
            name="Room",
            floor_area_m2=Decimal("20.00"),
            wall_perimeter_m=Decimal("18.00") if with_dims else None,
            wall_height_m=Decimal("2.50") if with_dims else None,
        )
        db.add(room)
        db.commit()
        return p.id
    finally:
        db.close()


def test_wall_area_computation_perimeter_times_height():
    project_id = _project_with_room(with_dims=True)
    db = SessionLocal()
    try:
        areas = compute_project_areas(db, project_id)
    finally:
        db.close()
    assert areas.total_wall_m2 == Decimal("45.00")


def test_paintable_total_is_wall_plus_ceiling():
    project_id = _project_with_room(with_dims=True)
    db = SessionLocal()
    try:
        areas = compute_project_areas(db, project_id)
    finally:
        db.close()
    assert areas.total_paintable_m2 == areas.total_wall_m2 + areas.total_ceiling_m2


def test_per_m2_uses_selected_basis():
    project_id = _project_with_room(with_dims=True)
    db = SessionLocal()
    try:
        pricing = get_or_create_project_pricing(db, project_id)
        pricing.rate_per_m2 = Decimal("100.00")
        takeoff = get_or_create_project_takeoff_settings(db, project_id)
        takeoff.m2_basis = "PAINTABLE_TOTAL"
        db.add_all([pricing, takeoff])
        db.commit()
        baseline, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()
    per_m2 = next(s for s in scenarios if s.mode == "PER_M2")
    assert baseline.total_m2 == Decimal("65.00")
    assert per_m2.price_ex_vat == Decimal("6500.00")


def test_takeoff_settings_page_shows_area_breakdown():
    _login()
    project_id = _project_with_room(with_dims=True)
    response = client.get(f"/projects/{project_id}/takeoff")
    assert response.status_code == 200
    assert "total_wall_m2 = 45.00" in response.text
    assert "total_paintable_m2 = 65.00" in response.text


def test_per_m2_invalid_when_missing_perimeter_height_and_basis_wall():
    project_id = _project_with_room(with_dims=False)
    db = SessionLocal()
    try:
        pricing = get_or_create_project_pricing(db, project_id)
        pricing.rate_per_m2 = Decimal("100.00")
        takeoff = get_or_create_project_takeoff_settings(db, project_id)
        takeoff.m2_basis = "WALL_AREA"
        db.add_all([pricing, takeoff])
        db.commit()
        _, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()

    per_m2 = next(s for s in scenarios if s.mode == "PER_M2")
    assert per_m2.invalid is True
    assert per_m2.price_ex_vat == Decimal("0.00")
    assert "MISSING_UNITS_M2" in per_m2.warnings


def test_new_takeoff_regression_case_paintable_total():
    project_id = _project_with_room(with_dims=True)
    db = SessionLocal()
    try:
        pricing = get_or_create_project_pricing(db, project_id)
        pricing.rate_per_m2 = Decimal("100.00")
        takeoff = get_or_create_project_takeoff_settings(db, project_id)
        takeoff.m2_basis = "PAINTABLE_TOTAL"
        db.add_all([pricing, takeoff])
        db.commit()
        baseline, scenarios = compute_pricing_scenarios(db, project_id)
    finally:
        db.close()

    per_m2 = next(s for s in scenarios if s.mode == "PER_M2")
    assert baseline.total_m2 == Decimal("65.00")
    assert per_m2.price_ex_vat == Decimal("6500.00")
