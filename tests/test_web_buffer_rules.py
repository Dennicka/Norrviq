from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.buffer_rule import BufferRule
from app.models.project import Project
from app.models.worktype import WorkType

client = TestClient(app)
settings = get_settings()


def _login_admin():
    return client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _create_project(name: str | None = None) -> int:
    db = SessionLocal()
    try:
        p = Project(name=name or f"P-{uuid4().hex[:8]}")
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def _create_worktype() -> int:
    db = SessionLocal()
    try:
        wt = WorkType(code=f"WT-{uuid4().hex[:8]}", category="wall", unit="M2", name_ru="WT", name_sv="WT", hours_per_unit=Decimal("1.00"), base_difficulty_factor=Decimal("1.0"), is_active=True)
        db.add(wt)
        db.commit()
        db.refresh(wt)
        return wt.id
    finally:
        db.close()


def test_buffer_rules_page_renders_with_no_rules():
    _login_admin()
    db = SessionLocal()
    try:
        db.query(BufferRule).delete()
        db.commit()
    finally:
        db.close()

    resp = client.get("/web/buffer-rules")
    assert resp.status_code == 200
    assert "No rules" in resp.text


def test_create_edit_delete_rule_via_web_form():
    _login_admin()
    project_id = _create_project()

    create_resp = client.post(
        "/web/buffer-rules",
        data={
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "12.50",
            "scope_type": "PROJECT",
            "scope_id": str(project_id),
            "priority": "10",
            "is_active": "on",
        },
        follow_redirects=True,
    )
    assert create_resp.status_code == 200
    assert "12.50 PERCENT" in create_resp.text

    db = SessionLocal()
    try:
        rule = db.query(BufferRule).order_by(BufferRule.id.desc()).first()
        assert rule is not None
        rule_id = rule.id
    finally:
        db.close()

    edit_resp = client.post(
        "/web/buffer-rules",
        data={
            "rule_id": str(rule_id),
            "kind": "RISK",
            "basis": "INTERNAL_COST",
            "unit": "PERCENT",
            "value": "15.00",
            "scope_type": "PROJECT",
            "scope_id": str(project_id),
            "priority": "25",
            "is_active": "on",
        },
        follow_redirects=True,
    )
    assert edit_resp.status_code == 200
    assert "15.00 PERCENT" in edit_resp.text

    del_resp = client.post(f"/web/buffer-rules/{rule_id}/delete", follow_redirects=True)
    assert del_resp.status_code == 200

    db = SessionLocal()
    try:
        assert db.get(BufferRule, rule_id) is None
    finally:
        db.close()


def test_effective_preview_and_pricing_buffer_box():
    _login_admin()
    project_id = _create_project()
    _create_worktype()

    db = SessionLocal()
    try:
        db.add(
            BufferRule(
                kind="RISK",
                basis="INTERNAL_COST",
                unit="PERCENT",
                value=Decimal("7.00"),
                scope_type="PROJECT",
                scope_id=project_id,
                priority=5,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    effective = client.get(f"/api/ui/buffer-rules/effective?project_id={project_id}")
    assert effective.status_code == 200
    payload = effective.json()
    assert payload["applied_rule_id"] is not None

    pricing = client.get(f"/projects/{project_id}/pricing")
    assert pricing.status_code == 200
    assert "Buffer applied" in pricing.text
    assert "#" in pricing.text and "/web/buffer-rules?rule_id=" in pricing.text

    db = SessionLocal()
    try:
        db.query(BufferRule).delete()
        db.commit()
    finally:
        db.close()

    pricing_without = client.get(f"/projects/{project_id}/pricing")
    assert "Buffer: none" in pricing_without.text
