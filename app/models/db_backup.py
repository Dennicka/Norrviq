import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, func

from app.db import Base


class BackupStatus(str, enum.Enum):
    OK = "OK"
    FAILED = "FAILED"


class DBBackup(Base):
    __tablename__ = "db_backups"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    filename = Column(String(255), nullable=False, unique=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(Enum(BackupStatus), nullable=False, default=BackupStatus.OK)
    error_message = Column(Text, nullable=True)
