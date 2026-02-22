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
    sku = Column(String, nullable=True)
    default_pack_size = Column(Numeric(12, 2), nullable=True)
    default_cost_per_unit_ex_vat = Column(Numeric(12, 2), nullable=True)
    default_sell_per_unit_ex_vat = Column(Numeric(12, 2), nullable=True)
    default_markup_pct = Column(Numeric(5, 2), nullable=True)
    vat_rate_pct = Column(Numeric(5, 2), nullable=False, default=25)
    default_price_per_unit = Column(Numeric(10, 2), nullable=True)
    moms_percent = Column(Numeric(5, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    comment = Column(String, nullable=True)

    cost_items = relationship("ProjectCostItem", back_populates="material")
    recipes = relationship("MaterialRecipe", back_populates="material")
