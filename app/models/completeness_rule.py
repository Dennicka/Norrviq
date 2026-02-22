from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.db import Base


class CompletenessRule(Base):
    __tablename__ = "completeness_rules"

    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    segment = Column(String(16), nullable=False, default="ANY", server_default="ANY")
    pricing_mode = Column(String(32), nullable=False, default="ANY", server_default="ANY")
    check_key = Column(String(128), nullable=False)
    weight = Column(Integer, nullable=False, default=0, server_default="0")
    severity = Column(String(16), nullable=False, default="WARNING", server_default="WARNING")
    message_ru = Column(Text, nullable=False)
    message_sv = Column(Text, nullable=False)
    hint_link = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
