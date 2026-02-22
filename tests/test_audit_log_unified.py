import json

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import User
from app.security import hash_password
from tests.utils.document_factory import create_stable_document_fixture

client = TestClient(app)


def _login(email: str, password: str):
    client.post("/login", data={"username": email, "password": password}, follow_redirects=False)


def _ensure_user(email: str, role: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, password_hash=hash_password("Pass#123456"), role=role)
            db.add(user)
            db.commit()
    finally:
        db.close()


def test_audit_log_appends_and_is_immutable():
    _login("admin.test@example.com", "Admin#Pass123")
    client.post("/logout", follow_redirects=False)
    db = SessionLocal()
    try:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        row.action = "changed"
        try:
            db.commit()
            assert False, "update must fail"
        except ValueError:
            db.rollback()
        try:
            db.delete(row)
            db.commit()
            assert False, "delete must fail"
        except ValueError:
            db.rollback()
    finally:
        db.close()


def test_audit_chain_hashes_valid():
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
        prev_hash = None
        for row in rows:
            payload = {
                "actor_user_id": row.actor_user_id,
                "actor_role": row.actor_role,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "request_id": row.request_id,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "severity": row.severity.value,
                "metadata_json": row.metadata_json,
            }
            import hashlib
            expected = hashlib.sha256(f"{prev_hash or ''}{json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}".encode("utf-8")).hexdigest()
            assert row.prev_hash == prev_hash
            assert row.hash == expected
            prev_hash = row.hash
    finally:
        db.close()


def test_audit_viewer_requires_admin_or_auditor():
    _ensure_user("audit-viewer@example.com", "viewer")
    _ensure_user("audit-auditor@example.com", "auditor")

    _login("audit-viewer@example.com", "Pass#123456")
    denied = client.get("/admin/audit")
    assert denied.status_code == 403

    _login("audit-auditor@example.com", "Pass#123456")
    allowed = client.get("/admin/audit")
    assert allowed.status_code == 200


def test_audit_records_created_on_invoice_issue():
    create_stable_document_fixture(enable_rot=True, issue_documents=True)
    db = SessionLocal()
    try:
        found = db.query(AuditLog).filter(AuditLog.action == "invoice_issued").count()
        assert found >= 1
    finally:
        db.close()


def test_export_csv_works():
    _login("admin.test@example.com", "Admin#Pass123")
    response = client.get("/admin/audit/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "action" in response.text
