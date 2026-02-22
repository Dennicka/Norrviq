from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.db import Base


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    floor_area_m2 = Column(Numeric(10, 2), nullable=True)
    wall_perimeter_m = Column(Numeric(10, 2), nullable=True)
    wall_height_m = Column(Numeric(10, 2), nullable=True)

    wall_area_m2 = Column(Numeric(10, 2), nullable=True)
    ceiling_area_m2 = Column(Numeric(10, 2), nullable=True)
    baseboard_length_m = Column(Numeric(10, 2), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="rooms")
    work_items = relationship("ProjectWorkItem", back_populates="room")
    paint_settings = relationship(
        "RoomPaintSettings",
        back_populates="room",
        uselist=False,
        cascade="all, delete-orphan",
    )
