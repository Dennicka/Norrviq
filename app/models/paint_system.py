from enum import Enum as PyEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class PaintSystemSurface(str, PyEnum):
    WALLS = "WALLS"
    CEILING = "CEILING"
    FLOOR = "FLOOR"
    PAINTABLE_TOTAL = "PAINTABLE_TOTAL"


class PaintSystem(Base):
    __tablename__ = "paint_systems"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_paint_systems_name_version"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    steps = relationship("PaintSystemStep", back_populates="paint_system", cascade="all, delete-orphan", order_by="PaintSystemStep.step_order")


class PaintSystemStep(Base):
    __tablename__ = "paint_system_steps"

    id = Column(Integer, primary_key=True, index=True)
    paint_system_id = Column(Integer, ForeignKey("paint_systems.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    target_surface = Column(Enum(PaintSystemSurface, name="paintsystemsurface"), nullable=False)
    recipe_id = Column(Integer, ForeignKey("material_recipes.id", ondelete="CASCADE"), nullable=False)
    override_coats_count = Column(Integer, nullable=True)
    override_waste_pct = Column(Numeric(5, 2), nullable=True)
    is_optional = Column(Boolean, nullable=False, default=False)

    paint_system = relationship("PaintSystem", back_populates="steps")
    recipe = relationship("MaterialRecipe")


class ProjectPaintSettings(Base):
    __tablename__ = "project_paint_settings"

    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    default_wall_paint_system_id = Column(Integer, ForeignKey("paint_systems.id", ondelete="SET NULL"), nullable=True)
    default_ceiling_paint_system_id = Column(Integer, ForeignKey("paint_systems.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="paint_settings")
    default_wall_paint_system = relationship("PaintSystem", foreign_keys=[default_wall_paint_system_id])
    default_ceiling_paint_system = relationship("PaintSystem", foreign_keys=[default_ceiling_paint_system_id])


class RoomPaintSettings(Base):
    __tablename__ = "room_paint_settings"

    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    wall_paint_system_id = Column(Integer, ForeignKey("paint_systems.id", ondelete="SET NULL"), nullable=True)
    ceiling_paint_system_id = Column(Integer, ForeignKey("paint_systems.id", ondelete="SET NULL"), nullable=True)

    room = relationship("Room", back_populates="paint_settings")
    wall_paint_system = relationship("PaintSystem", foreign_keys=[wall_paint_system_id])
    ceiling_paint_system = relationship("PaintSystem", foreign_keys=[ceiling_paint_system_id])
