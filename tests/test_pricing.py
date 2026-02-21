from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project
from app.models.project_pricing import ProjectPricing
from app.models.user import User
from app.security import hash_password
from app.services.pricing import PRICING_MODES, PricingValidationError, get_or_create_project_pricing, update_project_pricing

client = TestClient(app)
settings = get_settings()


def login(email: str, password: str):
    return client.post(
        "/login",
        data={"username": email, "password": password, "next": "/projects/"},
        follow_redirects=False,
    )


def ensure_user(email: str, role: str, password: str = "test-password"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()


def test_project_pricing_created_on_project_create():
    login(settings.admin_email, settings.admin_password)

    response = client.post(
        "/projects/new",
        data={"name": f"Pricing Project {uuid4().hex[:8]}", "status": "draft"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    project_id = int(location.rstrip("/").split("/")[-1])

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert pricing.mode == "HOURLY"
    finally:
        db.close()


def test_pricing_validation_by_mode():
    db = SessionLocal()
    try:
        project = Project(name=f"Validation project {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        pricing = get_or_create_project_pricing(db, project.id)

        for mode, required_field in {
            "FIXED_TOTAL": "fixed_total_price",
            "PER_M2": "rate_per_m2",
            "PER_ROOM": "rate_per_room",
            "PIECEWORK": "rate_per_piece",
        }.items():
            payload = {
                "mode": mode,
                "include_materials": "on",
                "include_travel_setup_buffers": "on",
                "currency": "SEK",
            }
            try:
                update_project_pricing(db, pricing=pricing, payload=payload, user_id="admin@example.com")
                assert False, f"Expected PricingValidationError for mode {mode}"
            except PricingValidationError as exc:
                assert required_field in exc.errors

        assert "HOURLY" in PRICING_MODES
    finally:
        db.close()


def test_pricing_screen_persists_values_after_save():
    login(settings.admin_email, settings.admin_password)
    db = SessionLocal()
    try:
        project = Project(name=f"Persist pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    save_response = client.post(
        f"/projects/{project_id}/pricing",
        data={
            "mode": "PIECEWORK",
            "rate_per_piece": "199.90",
            "target_margin_pct": "22.50",
            "include_materials": "on",
            "include_travel_setup_buffers": "on",
            "currency": "SEK",
        },
        follow_redirects=False,
    )
    assert save_response.status_code == 303

    page = client.get(f"/projects/{project_id}/pricing")
    assert page.status_code == 200
    assert 'value="PIECEWORK" checked' in page.text
    assert 'name="rate_per_piece" value="199.90"' in page.text
    assert 'name="target_margin_pct" value="22.50"' in page.text


def test_pricing_update_requires_role():
    ensure_user("pricing-viewer@example.com", "viewer")
    login("pricing-viewer@example.com", "test-password")

    db = SessionLocal()
    try:
        project = Project(name=f"RBAC pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"mode": "HOURLY", "currency": "SEK"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_pricing_post_requires_csrf():
    login(settings.admin_email, settings.admin_password)
    db = SessionLocal()
    try:
        project = Project(name=f"CSRF pricing {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/pricing",
        data={"mode": "HOURLY", "currency": "SEK"},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403
