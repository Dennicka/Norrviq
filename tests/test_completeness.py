from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.models.project_pricing import ProjectPricing
from app.models.room import Room
from app.models.user import User
from app.security import hash_password
from app.services.completeness import compute_completeness

client = TestClient(app)


def _login_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "cmp-admin@example.com").first():
            db.add(User(email="cmp-admin@example.com", password_hash=hash_password("Password#123"), role="admin"))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": "cmp-admin@example.com", "password": "Password#123"})


def _project(with_rooms: bool = True, with_m2: bool = True) -> int:
    db = SessionLocal()
    try:
        p = Project(name="Completeness Project")
        db.add(p)
        db.commit()
        db.refresh(p)
        db.add(ProjectPricing(project_id=p.id, mode="FIXED_TOTAL", fixed_total_price=Decimal("12000")))
        if with_rooms:
            db.add(Room(project_id=p.id, name="Room-1", floor_area_m2=Decimal("10") if with_m2 else Decimal("0"), wall_height_m=Decimal("2.6")))
        db.commit()
        return p.id
    finally:
        db.close()


def test_completeness_score_calculation_weights():
    project_id = _project(with_rooms=False)
    db = SessionLocal()
    try:
        report = compute_completeness(db, project_id, mode="FIXED_TOTAL", segment="ANY")
        assert 0 <= report.score <= 100
        assert report.level in {"LOW", "MEDIUM", "HIGH"}
        assert report.missing
    finally:
        db.close()


def test_completeness_blocks_per_m2_without_total_m2():
    project_id = _project(with_rooms=True, with_m2=False)
    db = SessionLocal()
    try:
        report = compute_completeness(db, project_id, mode="PER_M2", segment="ANY")
        assert report.can_issue_mode is False
        assert any(item.check_key == "HAS_TOTAL_M2" for item in report.missing)
    finally:
        db.close()


def test_completeness_blocks_fixed_below_threshold():
    project_id = _project(with_rooms=False)
    db = SessionLocal()
    try:
        policy = get_or_create_pricing_policy(db)
        policy.min_completeness_score_for_fixed = 95
        db.add(policy)
        db.commit()
        report = compute_completeness(db, project_id, mode="FIXED_TOTAL", segment="ANY")
        assert report.score < 95
        assert report.can_issue_mode is False
    finally:
        db.close()


def test_project_page_shows_confidence_meter():
    _login_admin()
    project_id = _project(with_rooms=False)
    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert "Completeness / Confidence" in response.text


def test_pricing_page_shows_score_per_mode():
    _login_admin()
    project_id = _project(with_rooms=True, with_m2=False)
    response = client.get(f"/projects/{project_id}/pricing")
    assert response.status_code == 200
    assert "score" in response.text


def test_finalize_blocked_by_completeness_when_fixed():
    _login_admin()
    project_id = _project(with_rooms=False)
    db = SessionLocal()
    try:
        invoice = Invoice(project_id=project_id, issue_date=date.today(), status="draft", work_sum_without_moms=Decimal("1"), moms_amount=Decimal("0"), rot_amount=Decimal("0"), client_pays_total=Decimal("1"))
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        invoice_id = invoice.id
    finally:
        db.close()

    offer_response = client.post(f"/offers/{project_id}/finalize", headers={"accept": "application/json"})
    assert offer_response.status_code == 409
    assert "недостаточно данных" in offer_response.json()["detail"].lower()

    invoice_response = client.post(f"/invoices/{invoice_id}/finalize", headers={"accept": "application/json"})
    assert invoice_response.status_code == 409
