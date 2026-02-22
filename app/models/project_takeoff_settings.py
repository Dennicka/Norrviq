from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db import Base

M2_BASIS_CHOICES = {"FLOOR_AREA", "WALL_AREA", "CEILING_AREA", "PAINTABLE_TOTAL"}
DEFAULT_M2_BASIS = "FLOOR_AREA"


class ProjectTakeoffSettings(Base):
    __tablename__ = "project_takeoff_settings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    m2_basis = Column(String(32), nullable=False, default=DEFAULT_M2_BASIS, server_default=DEFAULT_M2_BASIS)
    include_openings_subtraction = Column(Boolean, nullable=False, default=False, server_default="0")
    wall_area_formula_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="takeoff_settings")
