from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text, func

from app.db import Base


class SanityRule(Base):
    __tablename__ = "sanity_rules"

    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    entity = Column(String(32), nullable=False)
    field = Column(String(64), nullable=False)
    rule_type = Column(String(32), nullable=False)
    min_value = Column(Numeric(12, 2), nullable=True)
    max_value = Column(Numeric(12, 2), nullable=True)
    severity = Column(String(16), nullable=False)
    message_ru = Column(Text, nullable=False)
    message_sv = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), nullable=False)
