import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog, AuditSeverity
from app.models.user import User

SENSITIVE_KEYS = {"password", "secret", "csrf", "token", "authorization"}


def _sanitize(value: Any):
    if isinstance(value, dict):
        clean = {}
        for k, v in value.items():
            key = str(k)
            if any(flag in key.lower() for flag in SENSITIVE_KEYS):
                continue
            clean[key] = _sanitize(v)
        return clean
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    base = f"{prev_hash or ''}{_canonical_json(payload)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def log_event(
    db: Session,
    request: Request | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    severity: str = "INFO",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    metadata_payload = _sanitize(metadata or {})

    actor_user_id = None
    actor_role = None
    request_id = None
    ip_address = None
    user_agent = None
    if request is not None:
        actor_role = request.session.get("user_role") if hasattr(request, "session") else None
        email = request.session.get("user_email") if hasattr(request, "session") else None
        if email:
            user = db.query(User).filter(User.email == email).first()
            actor_user_id = user.id if user else None
        request_id = getattr(request.state, "request_id", None)
        ip_address = request.client.host if request.client else request.headers.get("x-forwarded-for")
        user_agent = request.headers.get("user-agent")

    prev = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = prev.hash if prev else None

    row = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        severity=AuditSeverity(severity),
        metadata_json=_canonical_json(metadata_payload),
        prev_hash=prev_hash,
        hash="",
    )
    hash_payload = {
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
    row.hash = _build_hash(prev_hash, hash_payload)
    db.add(row)
    db.flush()
    return row
