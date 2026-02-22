import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, event, func

from app.db import Base


class AuditSeverity(str, enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    SECURITY = "SECURITY"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role = Column(String(20), nullable=True)
    action = Column(String(128), nullable=False, index=True)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(64), nullable=True)
    request_id = Column(String(128), nullable=True, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    severity = Column(Enum(AuditSeverity), nullable=False, default=AuditSeverity.INFO)
    metadata_json = Column(Text, nullable=False, default="{}")
    hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=True)


@event.listens_for(AuditLog, "before_update", propagate=True)
def _audit_log_immutable_update(_mapper, _connection, _target):
    raise ValueError("audit_log is append-only")


@event.listens_for(AuditLog, "before_delete", propagate=True)
def _audit_log_immutable_delete(_mapper, _connection, _target):
    raise ValueError("audit_log is append-only")
