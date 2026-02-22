from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.user import User
from app.security import hash_password

client = TestClient(app)


def _login(email: str, password: str):
    return client.post("/login", data={"username": email, "password": password}, follow_redirects=False)


def _ensure_user(email: str, password: str, role: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email, password_hash=hash_password(password), role=role)
            db.add(user)
            db.commit()
    finally:
        db.close()


def test_backup_creates_file_and_metadata(tmp_path):
    settings = get_settings()
    settings.backup_dir = str(tmp_path)
    _login(settings.admin_email, settings.admin_password)

    r = client.post("/admin/backups/create", follow_redirects=True)
    assert r.status_code == 200

    db = SessionLocal()
    try:
        from app.models.db_backup import DBBackup

        row = db.query(DBBackup).order_by(DBBackup.id.desc()).first()
        assert row is not None
        p = Path(settings.backup_dir) / row.filename
        assert p.exists()
        assert p.with_suffix(p.suffix + ".sha256").exists()
        assert row.size_bytes > 0
        assert len(row.sha256) == 64
    finally:
        db.close()


def test_backup_download_requires_role(tmp_path):
    settings = get_settings()
    settings.backup_dir = str(tmp_path)
    _login(settings.admin_email, settings.admin_password)
    client.post("/admin/backups/create", follow_redirects=True)

    db = SessionLocal()
    try:
        from app.models.db_backup import DBBackup

        backup_id = db.query(DBBackup).order_by(DBBackup.id.desc()).first().id
    finally:
        db.close()

    _ensure_user("backup-viewer@example.com", "Viewer#123", "viewer")
    _login("backup-viewer@example.com", "Viewer#123")
    forbidden = client.get(f"/admin/backups/{backup_id}/download")
    assert forbidden.status_code == 403

    _ensure_user("backup-auditor@example.com", "Auditor#123", "auditor")
    _login("backup-auditor@example.com", "Auditor#123")
    ok = client.get(f"/admin/backups/{backup_id}/download")
    assert ok.status_code == 200


def test_restore_rejects_non_sqlite_file(tmp_path):
    settings = get_settings()
    settings.backup_dir = str(tmp_path)
    _login(settings.admin_email, settings.admin_password)

    bad = tmp_path / "not-sqlite.db"
    bad.write_text("hello")
    with bad.open("rb") as f:
        r = client.post("/admin/backups/restore", files={"upload_db": ("not-sqlite.db", f, "application/octet-stream")}, data={"confirmation_word": "RESTORE"})
    assert r.status_code == 400


def test_restore_requires_confirmation_word(tmp_path):
    settings = get_settings()
    settings.backup_dir = str(tmp_path)
    _login(settings.admin_email, settings.admin_password)

    db_file = Path(settings.database_url.removeprefix("sqlite:///"))
    with db_file.open("rb") as f:
        r = client.post("/admin/backups/restore", files={"upload_db": ("db.db", f, "application/octet-stream")}, data={"confirmation_word": "WRONG"})
    assert r.status_code == 400


def test_restore_runs_integrity_check(tmp_path, monkeypatch):
    settings = get_settings()
    settings.backup_dir = str(tmp_path)
    _login(settings.admin_email, settings.admin_password)

    from app.services import backup as backup_service

    called = {"ok": False}

    def _fake_integrity(_path):
        called["ok"] = True

    monkeypatch.setattr(backup_service, "_run_integrity_check", _fake_integrity)

    db_file = Path(settings.database_url.removeprefix("sqlite:///"))
    with db_file.open("rb") as f:
        r = client.post("/admin/backups/restore", files={"upload_db": ("db.db", f, "application/octet-stream")}, data={"confirmation_word": "RESTORE"})
    assert r.status_code in (200, 303)
    assert called["ok"] is True


def test_retention_policy_deletes_old_backups(tmp_path):
    settings = get_settings()
    settings.backup_dir = str(tmp_path)
    settings.backup_max_files = 1
    settings.backup_retention_days = 365
    _login(settings.admin_email, settings.admin_password)

    client.post("/admin/backups/create", follow_redirects=True)
    client.post("/admin/backups/create", follow_redirects=True)

    db = SessionLocal()
    try:
        from app.models.db_backup import DBBackup

        rows = db.query(DBBackup).all()
        assert len(rows) == 1
        files = list(Path(settings.backup_dir).glob("backup_*.db"))
        assert len(files) == 1
    finally:
        db.close()
