import enum

from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.db import Base


class RoundingMode(str, enum.Enum):
    CEIL_TO_PACKS = "CEIL_TO_PACKS"
    NONE = "NONE"


class ProjectProcurementSettings(Base):
    __tablename__ = "project_procurement_settings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    preferred_supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    allow_substitutions = Column(Boolean, nullable=False, default=True)
    auto_select_cheapest = Column(Boolean, nullable=False, default=False)
    rounding_mode = Column(Enum(RoundingMode, name="procurement_rounding_mode"), nullable=False, default=RoundingMode.CEIL_TO_PACKS)

    project = relationship("Project", back_populates="procurement_settings")
    preferred_supplier = relationship("Supplier")
