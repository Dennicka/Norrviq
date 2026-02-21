from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.buffer_rule import BufferRule
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

client = TestClient(app)
settings = get_settings()


def _login_admin():
    return client.post("/login", data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"}, follow_redirects=False)


def _ensure_admin_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == settings.admin_email).first()
        if not user:
            db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password), role="admin"))
            db.commit()
    finally:
        db.close()


def _project_id() -> int:
    db = SessionLocal()
    try:
        p = Project(name="Buffer API Project")
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_buffer_rules_crud_list_and_effective_endpoint():
    db = SessionLocal()
    try:
        db.query(User).filter(User.email == settings.admin_email).delete()
        db.query(BufferRule).delete()
        db.commit()
    finally:
        db.close()

    _ensure_admin_user()
    _login_admin()
    project_id = _project_id()

    create_global = client.post(
        "/api/ui/buffer-rules",
        json={
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "10.00",
            "scope_type": "GLOBAL",
            "scope_id": None,
            "priority": 1,
            "is_active": True,
        },
    )
    assert create_global.status_code == 201
    global_rule = create_global.json()

    create_project = client.post(
        "/api/ui/buffer-rules",
        json={
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "15.00",
            "scope_type": "PROJECT",
            "scope_id": project_id,
            "priority": 100,
            "is_active": True,
        },
    )
    assert create_project.status_code == 201
    project_rule = create_project.json()

    list_resp = client.get(f"/api/ui/buffer-rules?project_id={project_id}&active=true")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == project_rule["id"]

    effective_resp = client.get(f"/api/ui/buffer-rules/effective?project_id={project_id}")
    assert effective_resp.status_code == 200
    effective = effective_resp.json()
    assert effective["applied_rule_id"] == project_rule["id"]
    assert effective["buffer_value"] == "15.00"

    update_resp = client.patch(
        f"/api/ui/buffer-rules/{project_rule['id']}",
        json={
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "12.50",
            "scope_type": "PROJECT",
            "scope_id": project_id,
            "priority": 90,
            "is_active": True,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["value"] == "12.50"

    delete_resp = client.delete(f"/api/ui/buffer-rules/{project_rule['id']}")
    assert delete_resp.status_code == 204

    effective_after_delete = client.get(f"/api/ui/buffer-rules/effective?project_id={project_id}")
    assert effective_after_delete.status_code == 200
    assert effective_after_delete.json()["applied_rule_id"] == global_rule["id"]


def test_buffer_rules_validation_percent_and_fk():
    db = SessionLocal()
    try:
        db.query(User).filter(User.email == settings.admin_email).delete()
        db.query(BufferRule).delete()
        db.commit()
    finally:
        db.close()

    _ensure_admin_user()
    _login_admin()

    invalid_percent = client.post(
        "/api/ui/buffer-rules",
        json={
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "150.00",
            "scope_type": "GLOBAL",
            "scope_id": None,
            "priority": 1,
            "is_active": True,
        },
    )
    assert invalid_percent.status_code == 400

    missing_project = client.post(
        "/api/ui/buffer-rules",
        json={
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "10.00",
            "scope_type": "PROJECT",
            "scope_id": 999999,
            "priority": 1,
            "is_active": True,
        },
    )
    assert missing_project.status_code == 404
