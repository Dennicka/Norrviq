from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class CostCategory(Base):
    __tablename__ = "cost_categories"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    name_ru = Column(String(255), nullable=False)
    name_sv = Column(String(255), nullable=False)

    project_cost_items = relationship("ProjectCostItem", back_populates="category")


class ProjectCostItem(Base):
    __tablename__ = "project_cost_items"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    cost_category_id = Column(Integer, ForeignKey("cost_categories.id"), nullable=False)
    title = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    moms_amount = Column(Numeric(12, 2), nullable=True)
    comment = Column(Text, nullable=True)
    is_material = Column(Boolean, nullable=False, default=True)

    project = relationship("Project", back_populates="cost_items")
    category = relationship("CostCategory", back_populates="project_cost_items")
