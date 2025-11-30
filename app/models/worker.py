from sqlalchemy import Boolean, Column, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.db import Base


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(100), nullable=True)
    hourly_rate = Column(Numeric(10, 2), nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    assignments = relationship("ProjectWorkerAssignment", back_populates="worker")
