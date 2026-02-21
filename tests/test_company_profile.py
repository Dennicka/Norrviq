from decimal import Decimal
from pathlib import Path
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.company_profile import CompanyProfile, get_or_create_company_profile
from app.models.project import Project, ProjectWorkItem
from app.models.user import User
from app.models.worktype import WorkType
from app.security import hash_password

client = TestClient(app)
settings = get_settings()


def _login(username: str, password: str, next_path: str = "/"):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": next_path},
        follow_redirects=False,
    )


def _create_offer_project() -> int:
    db = SessionLocal()
    try:
        db_client = Client(name=f"Offer Client {uuid.uuid4().hex[:6]}", address="Main street", is_rot_eligible=True)
        db.add(db_client)
        db.commit()
        db.refresh(db_client)

        wt = WorkType(
            code=f"CP-{uuid.uuid4().hex[:8]}",
            category="paint",
            unit="h",
            name_ru="Работа",
            description_ru="Описание",
            name_sv="Arbete",
            description_sv="Beskrivning",
            hours_per_unit=Decimal("1.0"),
            base_difficulty_factor=Decimal("1.0"),
        )
        db.add(wt)
        db.commit()
        db.refresh(wt)

        project = Project(name="Offer Test", client_id=db_client.id, address="Addr")
        db.add(project)
        db.commit()
        db.refresh(project)

        item = ProjectWorkItem(project_id=project.id, work_type_id=wt.id, quantity=Decimal("2"), difficulty_factor=Decimal("1"))
        db.add(item)
        db.commit()
        return project.id
    finally:
        db.close()


def test_company_profile_singleton_upsert():
    db = SessionLocal()
    try:
        first = get_or_create_company_profile(db)
        second = get_or_create_company_profile(db)
        assert first.id == 1
        assert second.id == 1
        assert db.query(CompanyProfile).count() == 1
    finally:
        db.close()


def test_company_profile_requires_admin():
    db = SessionLocal()
    try:
        for email, role in (("viewer-cp@example.com", "viewer"), ("operator-cp@example.com", "operator")):
            if not db.query(User).filter(User.email == email).first():
                db.add(User(email=email, password_hash=hash_password("role-password"), role=role))
        db.commit()
    finally:
        db.close()

    client.get("/logout")
    _login("viewer-cp@example.com", "role-password", "/settings/company")
    viewer_resp = client.get("/settings/company", follow_redirects=False)
    assert viewer_resp.status_code == 403

    client.get("/logout")
    _login("operator-cp@example.com", "role-password", "/settings/company")
    operator_resp = client.get("/settings/company", follow_redirects=False)
    assert operator_resp.status_code == 403


def test_offer_template_uses_company_profile():
    db = SessionLocal()
    try:
        profile = get_or_create_company_profile(db)
        profile.legal_name = "Trenor Måleri AB"
        profile.org_number = "5561234567"
        profile.address_line1 = "Adress 1"
        profile.postal_code = "11122"
        profile.city = "Stockholm"
        profile.country = "Sverige"
        profile.email = "billing@trenor.se"
        profile.bankgiro = "123-4567"
        db.add(profile)
        db.commit()
    finally:
        db.close()

    project_id = _create_offer_project()
    _login(settings.admin_email, settings.admin_password)
    response = client.get(f"/projects/{project_id}/offer?lang=sv")
    assert response.status_code == 200
    assert "Trenor Måleri AB" in response.text


def test_no_hardcoded_norrviq():
    for base in (Path("app"), Path("app/templates")):
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".html", ".md", ".js", ".css"}:
                content = path.read_text(encoding="utf-8", errors="ignore")
                assert "Norrviq" not in content, f"Forbidden hardcoded company name in {path}"
