from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MaterialConsumptionOverride(Base):
    __tablename__ = "material_consumption_overrides"
    __table_args__ = (
        CheckConstraint("quantity_per_unit > 0", name="ck_mco_quantity_per_unit_positive"),
        CheckConstraint("base_unit_size > 0", name="ck_mco_base_unit_size_positive"),
        UniqueConstraint(
            "project_id",
            "room_id",
            "work_type_id",
            "material_id",
            "surface_kind",
            "unit_basis",
            "is_active",
            name="uq_mco_scope_active",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True, index=True)
    work_type_id = Column(Integer, ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    surface_kind = Column(String(20), nullable=False)
    unit_basis = Column(String(20), nullable=False)
    quantity_per_unit = Column(Numeric(12, 4), nullable=False)
    base_unit_size = Column(Numeric(12, 4), nullable=False, default=1)
    waste_factor_percent = Column(Numeric(6, 2), nullable=True)
    comment = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    project = relationship("Project")
    room = relationship("Room")
    work_type = relationship("WorkType")
    material = relationship("Material")
