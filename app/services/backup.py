import hashlib
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.audit import log_event
from app.config import get_settings
from app.db import engine
from app.maintenance import set_enabled
from app.models.db_backup import BackupStatus, DBBackup
from app.models.user import User

logger = logging.getLogger("uvicorn.error")


def _sqlite_db_path() -> Path:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        raise RuntimeError("Backup service only supports sqlite")
    db_path = settings.database_url.removeprefix("sqlite:///")
    return Path(db_path).resolve()


def _backup_dir() -> Path:
    d = Path(get_settings().backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d.resolve()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksum(path: Path, digest: str) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def _current_user_id(db: Session, email: str | None) -> int | None:
    if not email:
        return None
    u = db.query(User).filter(User.email == email).first()
    return u.id if u else None


def create_backup(db: Session, requested_by_email: str | None, notes: str | None = None) -> DBBackup:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"backup_{timestamp}.db"
    backup_path = _backup_dir() / filename
    created_by_user_id = _current_user_id(db, requested_by_email)

    row = DBBackup(
        filename=filename,
        size_bytes=0,
        sha256="",
        created_by_user_id=created_by_user_id,
        notes=notes,
        status=BackupStatus.FAILED,
    )
    db.add(row)
    db.flush()

    try:
        src = _sqlite_db_path()
        with sqlite3.connect(src) as source_conn:
            with sqlite3.connect(backup_path) as target_conn:
                source_conn.backup(target_conn)
                target_conn.execute("PRAGMA wal_checkpoint(FULL)")
                target_conn.commit()
        digest = _sha256(backup_path)
        _write_checksum(backup_path, digest)

        row.size_bytes = backup_path.stat().st_size
        row.sha256 = digest
        row.status = BackupStatus.OK
        row.error_message = None
        db.commit()
        db.refresh(row)

        logger.info("db_backup_created request_id=%s filename=%s status=%s", None, filename, row.status.value)
        log_event(db, None, "db_backup_created", entity_type="db_backup", entity_id=row.id, metadata={"filename": filename, "status": row.status.value})
        db.commit()

        apply_retention_policy(db)
        return row
    except Exception as exc:
        row.error_message = str(exc)
        db.commit()
        logger.exception("db_backup_failed filename=%s", filename)
        raise


def apply_retention_policy(db: Session) -> None:
    settings = get_settings()
    backups = db.query(DBBackup).filter(DBBackup.status == BackupStatus.OK).order_by(DBBackup.created_at.desc(), DBBackup.id.desc()).all()
    keep_ids = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.backup_retention_days)
    for i, b in enumerate(backups):
        if i < settings.backup_max_files and (b.created_at is None or b.created_at.replace(tzinfo=timezone.utc) >= cutoff):
            keep_ids.add(b.id)
    for b in backups:
        if b.id in keep_ids:
            continue
        delete_backup(db, b.id, actor_email=None, from_retention=True)


def list_backups(db: Session) -> list[DBBackup]:
    return db.query(DBBackup).order_by(DBBackup.created_at.desc(), DBBackup.id.desc()).all()


def get_backup_or_404(db: Session, backup_id: int) -> DBBackup:
    row = db.query(DBBackup).filter(DBBackup.id == backup_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Backup not found")
    return row


def backup_file_path(filename: str) -> Path:
    return _backup_dir() / filename


def verify_backup_checksum(db: Session, backup_id: int, actor_email: str | None) -> bool:
    row = get_backup_or_404(db, backup_id)
    path = backup_file_path(row.filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup file missing")
    is_ok = _sha256(path) == row.sha256
    log_event(db, None, "db_backup_verified", entity_type="db_backup", entity_id=row.id, metadata={"filename": row.filename, "status": "OK" if is_ok else "FAILED"})
    db.commit()
    return is_ok


def delete_backup(db: Session, backup_id: int, actor_email: str | None, from_retention: bool = False) -> None:
    row = get_backup_or_404(db, backup_id)
    file_path = backup_file_path(row.filename)
    checksum_path = file_path.with_suffix(file_path.suffix + ".sha256")
    if file_path.exists():
        file_path.unlink()
    if checksum_path.exists():
        checksum_path.unlink()
    db.delete(row)
    db.commit()
    log_event(db, None, "db_backup_deleted", entity_type="db_backup", entity_id=backup_id, metadata={"filename": row.filename, "status": "OK", "retention": from_retention})
    db.commit()


def _validate_sqlite_file(path: Path) -> None:
    with path.open("rb") as f:
        header = f.read(16)
    if header != b"SQLite format 3\x00":
        raise HTTPException(status_code=400, detail="Uploaded file is not a SQLite database")


def _run_integrity_check(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0].lower() != "ok":
        raise HTTPException(status_code=400, detail="integrity_check failed")


def _validate_alembic_compat(path: Path) -> None:
    expected_heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    current_heads = {r[0] for r in rows}
    if not current_heads:
        raise HTTPException(status_code=400, detail="Uploaded DB has no alembic version")
    if not current_heads.issubset(expected_heads):
        raise HTTPException(status_code=400, detail="Uploaded DB migration head is incompatible")


def restore_backup(db: Session, request_id: str | None, actor_email: str | None, upload_db: UploadFile, confirm_word: str, dry_run: bool = False, upload_sha256: UploadFile | None = None) -> str:
    if confirm_word != "RESTORE":
        raise HTTPException(status_code=400, detail="Confirmation word RESTORE is required")

    tmp_dir = _backup_dir() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    uploaded_path = tmp_dir / f"restore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"
    with uploaded_path.open("wb") as out:
        shutil.copyfileobj(upload_db.file, out)

    _validate_sqlite_file(uploaded_path)

    if upload_sha256 is not None:
        checksum_text = upload_sha256.file.read().decode("utf-8", errors="ignore").strip()
        expected_hash = checksum_text.split()[0] if checksum_text else ""
        if expected_hash and _sha256(uploaded_path) != expected_hash:
            raise HTTPException(status_code=400, detail="Uploaded DB checksum mismatch")

    _run_integrity_check(uploaded_path)
    _validate_alembic_compat(uploaded_path)

    live_db = _sqlite_db_path()
    pre_restore = _backup_dir() / f"pre_restore_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.db"

    set_enabled(True)
    try:
        if not dry_run:
            engine.dispose()
            shutil.copy2(live_db, pre_restore)
            swap_target = live_db.with_suffix(live_db.suffix + ".restore_new")
            shutil.copy2(uploaded_path, swap_target)
            os.replace(swap_target, live_db)
            command.upgrade(Config("alembic.ini"), "head")

        log_event(db, None, "db_backup_restored", entity_type="db_backup", entity_id=0, metadata={"filename": upload_db.filename, "status": "OK", "request_id": request_id})
        db.commit()
        return str(pre_restore)
    finally:
        set_enabled(False)
        if uploaded_path.exists():
            uploaded_path.unlink()
