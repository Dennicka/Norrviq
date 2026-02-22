import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.invoice import Invoice
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.sanity_rule import SanityRule
from app.models.user import User
from app.models.worktype import WorkType
from app.security import hash_password
from app.services.quality import evaluate_project_quality

client = TestClient(app)


def _login_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "dq-admin@example.com").first():
            db.add(User(email="dq-admin@example.com", password_hash=hash_password("Password#123"), role="admin"))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": "dq-admin@example.com", "password": "Password#123"})


def _project(with_block: bool = False) -> int:
    db = SessionLocal()
    try:
        wt = WorkType(
            code=f"DQ-WT-{uuid.uuid4()}",
            category="paint",
            unit="m2",
            name_ru="Тест",
            description_ru="",
            name_sv="Test",
            description_sv="",
            hours_per_unit=Decimal("1.0"),
            base_difficulty_factor=Decimal("1.0"),
        )
        db.add(wt)
        db.commit()
        db.refresh(wt)

        p = Project(name="DQ Project")
        db.add(p)
        db.commit()
        db.refresh(p)

        db.add(Room(project_id=p.id, name="Room", floor_area_m2=Decimal("12"), wall_height_m=Decimal("2.7"), wall_area_m2=Decimal("45"), ceiling_area_m2=Decimal("12")))
        qty = Decimal("0") if with_block else Decimal("10")
        db.add(ProjectWorkItem(project_id=p.id, work_type_id=wt.id, quantity=qty, difficulty_factor=Decimal("1.0")))
        db.commit()
        return p.id
    finally:
        db.close()


def test_quality_report_no_blocks_allows_issue():
    project_id = _project(with_block=False)
    db = SessionLocal()
    try:
        report = evaluate_project_quality(db, project_id)
        assert report.blocks_count == 0
        assert report.can_issue_documents is True
    finally:
        db.close()


def test_quality_blocks_prevent_offer_finalize():
    _login_admin()
    project_id = _project(with_block=True)
    response = client.post(f"/offers/{project_id}/finalize", headers={"accept": "application/json"})
    assert response.status_code == 409
    assert "issues" in response.json()


def test_quality_blocks_prevent_invoice_finalize():
    _login_admin()
    project_id = _project(with_block=True)
    db = SessionLocal()
    try:
        invoice = Invoice(project_id=project_id, issue_date=date.today(), status="draft", work_sum_without_moms=Decimal("100"), moms_amount=Decimal("25"), rot_amount=Decimal("0"), client_pays_total=Decimal("125"))
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        invoice_id = invoice.id
    finally:
        db.close()

    response = client.post(f"/invoices/{invoice_id}/finalize", headers={"accept": "application/json"})
    assert response.status_code == 409
    assert "issues" in response.json()


def test_seed_rules_exist_on_clean_db():
    db = SessionLocal()
    try:
        assert db.query(SanityRule).count() >= 12
    finally:
        db.close()


def test_ui_quality_panel_renders():
    _login_admin()
    project_id = _project(with_block=False)
    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert "Качество данных" in response.text


def test_settings_sanity_rules_admin_only():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "dq-viewer@example.com").first():
            db.add(User(email="dq-viewer@example.com", password_hash=hash_password("Viewer#123"), role="viewer"))
            db.commit()
    finally:
        db.close()

    client.get("/logout")
    client.post("/login", data={"username": "dq-viewer@example.com", "password": "Viewer#123"})
    response = client.get("/settings/sanity-rules", follow_redirects=False)
    assert response.status_code == 403
