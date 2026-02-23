from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectMaterialActualEntry(Base):
    __tablename__ = "project_material_actual_entries"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    material_name = Column(String(255), nullable=False)
    actual_qty = Column(Numeric(12, 4), nullable=False, default=0)
    actual_packages = Column(Numeric(12, 2), nullable=False, default=0)
    actual_cost_sek = Column(Numeric(12, 2), nullable=False, default=0)
    supplier = Column(String(255), nullable=True)
    receipt_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")
