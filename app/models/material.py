from sqlalchemy import Boolean, Column, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.db import Base


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    name_ru = Column(String, nullable=False)
    name_sv = Column(String, nullable=False)
    category = Column(String, nullable=True)
    unit = Column(String, nullable=False)
    default_price_per_unit = Column(Numeric(10, 2), nullable=True)
    moms_percent = Column(Numeric(5, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    comment = Column(String, nullable=True)

    cost_items = relationship("ProjectCostItem", back_populates="material")
