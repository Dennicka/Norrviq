from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import relationship

from app.db import Base


class ProjectMaterialSettings(Base):
    __tablename__ = "project_material_settings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    default_markup_pct = Column(Numeric(5, 2), nullable=False, default=20)
    use_material_sell_price = Column(Boolean, nullable=False, default=False)
    include_materials_in_pricing = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="material_settings")
