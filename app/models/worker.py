from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.db import Base


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(100), nullable=True)
    hourly_rate = Column(Numeric(10, 2), nullable=True)
    default_tax_percent_for_net = Column(Numeric(5, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="1")
    default_speed_profile_id = Column(Integer, ForeignKey("speed_profiles.id"), nullable=True)

    assignments = relationship("ProjectWorkerAssignment", back_populates="worker")
    default_speed_profile = relationship("SpeedProfile")
