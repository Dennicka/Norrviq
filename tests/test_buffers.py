from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.buffer_rule import BufferRule
from app.models.project import Project
from app.models.project_buffer_settings import ProjectBufferSettings
from app.models.user import User
from app.security import hash_password
from app.services.pricing import compute_project_baseline

client = TestClient(app)
settings = get_settings()


def _login(email: str, password: str):
    return client.post("/login", data={"username": email, "password": password, "next": "/projects/"}, follow_redirects=False)


def _ensure_user(email: str, role: str, password: str = "test-password"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()




def _reset_rules(db):
    db.query(BufferRule).delete()
    db.commit()

def _project() -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"Buffers {uuid4().hex[:8]}")
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_buffers_default_zero_does_not_change_baseline():
    pid = _project()
    db = SessionLocal()
    try:
        _reset_rules(db)
        baseline = compute_project_baseline(db, pid, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.buffers_hours_total == Decimal("0.00")
        assert baseline.buffers_cost_total == Decimal("0.00")
        assert baseline.raw_labor_hours_total == baseline.labor_hours_total
        assert baseline.raw_internal_cost == baseline.internal_total_cost
    finally:
        db.close()


def test_buffer_rule_precedence_project_over_global():
    pid = _project()
    db = SessionLocal()
    try:
        _reset_rules(db)
        db.add(BufferRule(kind="SETUP", basis="LABOR_HOURS", unit="FIXED_HOURS", value=Decimal("1.00"), scope_type="GLOBAL", scope_id=None, priority=0, is_active=True))
        db.add(BufferRule(kind="SETUP", basis="LABOR_HOURS", unit="FIXED_HOURS", value=Decimal("2.00"), scope_type="PROJECT", scope_id=pid, priority=100, is_active=True))
        db.commit()
        baseline = compute_project_baseline(db, pid, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.buffers_hours_total == Decimal("3.00")
        assert len(baseline.buffers) == 2
        assert baseline.buffers[0]["scope_type"] == "PROJECT"
    finally:
        db.close()


def test_fixed_and_percent_applied_correctly():
    pid = _project()
    db = SessionLocal()
    try:
        _reset_rules(db)
        db.add(BufferRule(kind="RISK", basis="INTERNAL_COST", unit="FIXED_SEK", value=Decimal("100.00"), scope_type="GLOBAL", scope_id=None, priority=0, is_active=True))
        db.add(BufferRule(kind="RISK", basis="INTERNAL_COST", unit="PERCENT", value=Decimal("10.00"), scope_type="GLOBAL", scope_id=None, priority=0, is_active=True))
        db.commit()
        baseline = compute_project_baseline(db, pid, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.buffers_cost_total == Decimal("100.00")
    finally:
        db.close()


def test_pricing_details_show_buffers_breakdown_when_configured():
    _login(settings.admin_email, settings.admin_password)
    pid = _project()
    db = SessionLocal()
    try:
        _reset_rules(db)
        db.add(BufferRule(kind="SETUP", basis="LABOR_HOURS", unit="FIXED_HOURS", value=Decimal("0.50"), scope_type="PROJECT", scope_id=pid, priority=10, is_active=True))
        db.commit()
    finally:
        db.close()
    page = client.get(f"/projects/{pid}/pricing")
    assert page.status_code == 200
    assert "Raw baseline:" in page.text
    assert "Buffers breakdown:" in page.text


def test_settings_buffers_admin_only():
    _ensure_user("buffers-viewer@example.com", "viewer")
    _login("buffers-viewer@example.com", "test-password")
    resp = client.get("/settings/buffers")
    assert resp.status_code == 403


def test_buffers_post_requires_csrf():
    _login(settings.admin_email, settings.admin_password)
    pid = _project()
    response = client.post(
        f"/projects/{pid}/buffers",
        data={"include_setup_cleanup_travel": "on", "include_risk": "on"},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_golden_projects_baseline_unchanged_without_rules():
    pid = _project()
    db = SessionLocal()
    try:
        _reset_rules(db)
        db.add(ProjectBufferSettings(project_id=pid, include_setup_cleanup_travel=True, include_risk=True))
        db.commit()
        baseline = compute_project_baseline(db, pid, include_materials=True, include_travel_setup_buffers=True)
        assert baseline.buffers_hours_total == Decimal("0.00")
        assert baseline.buffers_cost_total == Decimal("0.00")
    finally:
        db.close()
