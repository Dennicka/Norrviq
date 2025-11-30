from sqlalchemy import Boolean, Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    contact_person = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    is_private_person = Column(Boolean, nullable=False, default=True)
    is_rot_eligible = Column(Boolean, nullable=False, default=True)

    projects = relationship("Project", back_populates="client")
