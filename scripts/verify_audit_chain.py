import hashlib
import json

from app.db import SessionLocal
from app.models.audit_log import AuditLog


def canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run() -> int:
    db = SessionLocal()
    try:
        prev_hash = None
        for row in db.query(AuditLog).order_by(AuditLog.id.asc()):
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
            expected = hashlib.sha256(f"{prev_hash or ''}{canonical(payload)}".encode("utf-8")).hexdigest()
            if row.prev_hash != prev_hash or row.hash != expected:
                print(f"BROKEN at id={row.id}")
                return 1
            prev_hash = row.hash
        print("OK")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
