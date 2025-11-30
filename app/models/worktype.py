from decimal import Decimal

from sqlalchemy import Boolean, Column, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


WORKTYPE_UNITS = [
    ("m2", "Square meters"),
    ("m", "Meters"),
    ("piece", "Piece"),
    ("room", "Room"),
    ("window", "Window"),
    ("door", "Door"),
    ("radiator", "Radiator"),
]


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

    @property
    def minutes_per_unit(self) -> int | None:
        if self.hours_per_unit is None:
            return None
        return int(round(float(self.hours_per_unit) * 60))

    def set_minutes_per_unit(self, minutes: int | None) -> None:
        if minutes is None:
            self.hours_per_unit = None
            return
        self.hours_per_unit = Decimal(minutes) / Decimal(60)
