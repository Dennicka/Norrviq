from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.db import Base


class MaterialRecipe(Base):
    __tablename__ = "material_recipes"
    __table_args__ = (
        CheckConstraint(
            "(applies_to = 'WORKTYPE' AND work_type_id IS NOT NULL) OR (applies_to = 'PROJECT' AND work_type_id IS NULL)",
            name="ck_material_recipes_applies_to_work_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    name = Column(String, nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    applies_to = Column(String(20), nullable=False, default="PROJECT")
    work_type_id = Column(Integer, ForeignKey("work_types.id", ondelete="SET NULL"), nullable=True)
    basis = Column(String(32), nullable=False)
    consumption_per_m2 = Column(Numeric(12, 4), nullable=False)
    coats_count = Column(Integer, nullable=False, default=1)
    waste_pct = Column(Numeric(5, 2), nullable=False, default=0)
    rounding_mode = Column(String(20), nullable=False, default="NONE")
    pack_size_override = Column(Numeric(12, 2), nullable=True)
    priority = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    material = relationship("Material", back_populates="recipes")
    work_type = relationship("WorkType")
