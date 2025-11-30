from sqlalchemy import Boolean, Column, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class WorkType(Base):
    __tablename__ = "work_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    category = Column(String(50), nullable=True)
    unit = Column(String(20), nullable=False)
    name_ru = Column(String(255), nullable=False)
    description_ru = Column(Text, nullable=True)
    name_sv = Column(String(255), nullable=False)
    description_sv = Column(Text, nullable=True)
    hours_per_unit = Column(Numeric(10, 4), nullable=False)
    base_difficulty_factor = Column(Numeric(5, 2), nullable=False, default=1.0)
    is_active = Column(Boolean, nullable=False, default=True)

    project_work_items = relationship("ProjectWorkItem", back_populates="work_type")
