import json
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.buffer_rule import BufferRule
from app.models.project import Project

client = TestClient(app)
settings = get_settings()


def _login_admin():
    return client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _project_id() -> int:
    db = SessionLocal()
    try:
        p = Project(name=f"Audit-{uuid4().hex[:8]}")
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_buffer_rule_audit_events_and_history_visible():
    _login_admin()
    project_id = _project_id()

    client.post(
        "/web/buffer-rules",
        data={
            "kind": "SETUP",
            "basis": "LABOR_HOURS",
            "unit": "FIXED_HOURS",
            "value": "1.25",
            "scope_type": "PROJECT",
            "scope_id": str(project_id),
            "priority": "1",
            "is_active": "on",
        },
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        rule = db.query(BufferRule).order_by(BufferRule.id.desc()).first()
        client.post(
            "/web/buffer-rules",
            data={
                "rule_id": str(rule.id),
                "kind": "SETUP",
                "basis": "LABOR_HOURS",
                "unit": "FIXED_HOURS",
                "value": "1.50",
                "scope_type": "PROJECT",
                "scope_id": str(project_id),
                "priority": "2",
                "is_active": "on",
            },
            follow_redirects=False,
        )
        client.post(f"/web/buffer-rules/{rule.id}/delete", follow_redirects=False)

        events = db.query(AuditEvent).filter(AuditEvent.entity_type == "buffer_rule").order_by(AuditEvent.id.desc()).limit(3).all()
        actions = [json.loads(e.details).get("action") for e in events]
        assert "DELETE" in actions
        assert "UPDATE" in actions
        assert "CREATE" in actions
    finally:
        db.close()

    history = client.get(f"/web/buffer-rules?project_id={project_id}")
    assert history.status_code == 200
    assert "History" in history.text
    assert "buffer_rule" in history.text


def test_project_buffer_settings_audit_event_written():
    _login_admin()
    project_id = _project_id()
    resp = client.post(
        f"/projects/{project_id}/buffers",
        data={"include_setup_cleanup_travel": "on"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db = SessionLocal()
    try:
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_type == "project_buffer_settings", AuditEvent.entity_id == project_id)
            .order_by(AuditEvent.id.desc())
            .first()
        )
        assert event is not None
        details = json.loads(event.details)
        assert details["action"] == "UPDATE"
        assert details["after_json"]["include_setup_cleanup_travel"] is True
    finally:
        db.close()
