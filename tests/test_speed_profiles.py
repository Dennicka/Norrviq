from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkerAssignment
from app.models.speed_profile import SpeedProfile
from app.models.user import User
from app.models.worker import Worker
from app.security import hash_password
from app.services.pricing import compute_project_baseline, get_or_create_project_pricing

client = TestClient(app)
settings = get_settings()


def _login(email: str, password: str, role: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": password, "next": "/projects/"}, follow_redirects=False)


def _make_project(hours: Decimal = Decimal("10.00")) -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"Speed-{uuid4().hex[:8]}")
        w = Worker(name=f"W-{uuid4().hex[:6]}", hourly_rate=Decimal("200.00"), is_active=True)
        db.add_all([p, w])
        db.flush()
        db.add(ProjectWorkerAssignment(project_id=p.id, worker_id=w.id, planned_hours=hours, actual_hours=hours))
        db.commit()
        get_or_create_project_pricing(db, p.id)
        return p.id
    finally:
        db.close()


def test_default_speed_is_medium_1_0():
    project_id = _make_project()
    db = SessionLocal()
    try:
        baseline = compute_project_baseline(db, project_id, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.speed_profile_code == "MEDIUM"
        assert baseline.speed_multiplier == Decimal("1.000")
        assert baseline.labor_hours_after_speed == baseline.raw_labor_hours_total
    finally:
        db.close()


def test_speed_multiplier_applies_to_labor_hours():
    project_id = _make_project(Decimal("10.00"))
    db = SessionLocal()
    try:
        fast = db.query(SpeedProfile).filter(SpeedProfile.code == "FAST").first()
        db.execute(
            text("INSERT INTO project_execution_profiles(project_id,speed_profile_id,apply_scope) VALUES (:pid,:sid,'PROJECT')"),
            {"pid": project_id, "sid": fast.id},
        )
        db.commit()

        baseline = compute_project_baseline(db, project_id, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.speed_multiplier == Decimal("0.850")
        assert baseline.labor_hours_after_speed == Decimal("8.50")
    finally:
        db.close()


def test_speed_breakdown_exposed():
    project_id = _make_project(Decimal("12.00"))
    db = SessionLocal()
    try:
        slow = db.query(SpeedProfile).filter(SpeedProfile.code == "SLOW").first()
        db.execute(
            text("INSERT INTO project_execution_profiles(project_id,speed_profile_id,apply_scope) VALUES (:pid,:sid,'PROJECT')"),
            {"pid": project_id, "sid": slow.id},
        )
        db.commit()

        baseline = compute_project_baseline(db, project_id, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.speed_profile_code == "SLOW"
        assert baseline.speed_hours_delta == Decimal("2.40")
    finally:
        db.close()


def test_pricing_details_show_speed_section():
    _login(settings.admin_email, settings.admin_password, "admin")
    project_id = _make_project()
    resp = client.get(f"/projects/{project_id}/pricing")
    assert resp.status_code == 200
    assert "Speed multiplier applied" in resp.text
    assert "Labor hours after speed" in resp.text


def test_project_speed_requires_role():
    _login("viewer-speed@example.com", "Viewer#Pass123", "viewer")
    project_id = _make_project()
    resp = client.post(
        f"/projects/{project_id}/buffers",
        data={"speed_profile_id": "", "include_setup_cleanup_travel": "on", "include_risk": "on"},
    )
    assert resp.status_code == 403


def test_speed_settings_admin_only():
    _login("operator-speed@example.com", "Operator#Pass123", "operator")
    resp = client.get("/settings/speed-profiles")
    assert resp.status_code == 403
