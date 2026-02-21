from sqlalchemy import Column, Integer, String

from app.db import Base
from app.security import ADMIN_ROLE


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(512), nullable=False)
    role = Column(String(20), nullable=False, default=ADMIN_ROLE)
