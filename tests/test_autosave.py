from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.user import User
from app.models.worktype import WorkType
from app.security import ADMIN_ROLE, VIEWER_ROLE, hash_password
from app.services.pricing import get_or_create_project_pricing

client = TestClient(app)


def _ensure_user(email: str, role: str, password: str = "Password#123"):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()


def _login(email: str, password: str = "Password#123"):
    return client.post("/login", data={"username": email, "password": password, "next": "/projects/"}, follow_redirects=False)


def _seed_project() -> tuple[int, int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f"Autosave {uuid4().hex[:6]}")
        db.add(p)
        db.flush()

        r = Room(project_id=p.id, name="Living", floor_area_m2=Decimal("10.00"))
        db.add(r)

        wt = WorkType(code=f"AS-{uuid4().hex[:6]}", category="paint", unit="m2", name_ru="Тест", name_sv="Test", hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        db.add(wt)
        db.flush()

        item = ProjectWorkItem(project_id=p.id, work_type_id=wt.id, room_id=r.id, quantity=Decimal("1.00"), difficulty_factor=Decimal("1.00"))
        db.add(item)
        db.commit()
        get_or_create_project_pricing(db, p.id)
        db.commit()
        return p.id, r.id, item.id
    finally:
        db.close()


def test_room_patch_updates_partial():
    _ensure_user("autosave-op@example.com", ADMIN_ROLE)
    _login("autosave-op@example.com")
    project_id, room_id, _ = _seed_project()

    response = client.patch(f"/api/projects/{project_id}/rooms/{room_id}", json={"name": "Kitchen"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "request_id" in payload

    db = SessionLocal()
    try:
        room = db.get(Room, room_id)
        assert room.name == "Kitchen"
        assert room.floor_area_m2 == Decimal("10.00")
    finally:
        db.close()


def test_pricing_patch_validates_and_returns_field_errors():
    _ensure_user("autosave-pricing@example.com", ADMIN_ROLE)
    _login("autosave-pricing@example.com")
    project_id, _, _ = _seed_project()

    response = client.patch(f"/api/projects/{project_id}/pricing", json={"target_margin_pct": "120"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation"
    assert "target_margin_pct" in payload["fields"]
    assert payload.get("request_id") is not None


def test_patch_requires_csrf_and_role():
    _ensure_user("autosave-viewer@example.com", VIEWER_ROLE)
    _login("autosave-viewer@example.com")
    project_id, room_id, item_id = _seed_project()

    forbidden = client.patch(f"/api/projects/{project_id}/rooms/{room_id}", json={"name": "Denied"})
    assert forbidden.status_code == 403

    _ensure_user("autosave-admin@example.com", ADMIN_ROLE)
    _login("autosave-admin@example.com")
    no_csrf = client.patch(
        f"/api/projects/{project_id}/work-items/{item_id}",
        json={"quantity": "2"},
        headers={"X-No-Auto-CSRF": "1"},
    )
    assert no_csrf.status_code == 403


def test_templates_include_autosave_markers():
    _ensure_user("autosave-markers@example.com", ADMIN_ROLE)
    _login("autosave-markers@example.com")
    project_id, room_id, item_id = _seed_project()

    room_page = client.get(f"/projects/{project_id}/rooms/{room_id}/edit")
    item_page = client.get(f"/projects/{project_id}/items/{item_id}/edit")
    pricing_page = client.get(f"/projects/{project_id}/pricing")

    assert "js/autosave.js" in room_page.text
    assert 'data-autosave="true"' in item_page.text
    assert '/api/projects/' in pricing_page.text
