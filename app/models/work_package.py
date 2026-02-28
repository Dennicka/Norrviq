from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class WorkPackageTemplate(Base):
    __tablename__ = "work_package_templates"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name_ru = Column(String(255), nullable=False)
    name_sv = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=False)
    description_ru = Column(Text, nullable=True)
    description_sv = Column(Text, nullable=True)
    description_en = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    items = relationship(
        "WorkPackageTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkPackageTemplateItem.sort_order",
    )


class WorkPackageTemplateItem(Base):
    __tablename__ = "work_package_template_items"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("work_package_templates.id"), nullable=False, index=True)
    work_type_code = Column(String(64), nullable=False)
    scope_mode = Column(String(16), nullable=False, default="PROJECT")
    basis_type = Column(String(32), nullable=False, default="wall_area_m2")
    pricing_mode = Column(String(20), nullable=False, default="HOURLY")
    coats = Column(Numeric(10, 2), nullable=True)
    layers = Column(Numeric(10, 2), nullable=True)
    norm_hours_per_unit = Column(Numeric(12, 4), nullable=True)
    unit_rate_ex_vat = Column(Numeric(12, 2), nullable=True)
    hourly_rate_ex_vat = Column(Numeric(12, 2), nullable=True)
    fixed_total_ex_vat = Column(Numeric(12, 2), nullable=True)
    difficulty_factor = Column(Numeric(5, 2), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    template = relationship("WorkPackageTemplate", back_populates="items")
