from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, func

from app.db import Base


class SpeedProfile(Base):
    __tablename__ = "speed_profiles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), nullable=False, unique=True)
    name_ru = Column(String(255), nullable=False)
    name_sv = Column(String(255), nullable=False)
    multiplier = Column(Numeric(6, 3), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="1")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
