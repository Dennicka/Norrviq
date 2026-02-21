import json

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def log_buffer_audit(
    db: Session,
    *,
    actor: str | None,
    action: str,
    entity_type: str,
    entity_id: int,
    before: dict | None,
    after: dict | None,
    request_id: str | None,
) -> None:
    db.add(
        AuditEvent(
            event_type=f"{entity_type}_{action.lower()}",
            user_id=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(
                {
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "before_json": before,
                    "after_json": after,
                    "request_id": request_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    )
