from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, Numeric, String, func

from app.db import Base


class BufferRule(Base):
    __tablename__ = "buffer_rules"

    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    kind = Column(String(16), nullable=False)
    basis = Column(String(24), nullable=False)
    unit = Column(String(16), nullable=False)
    value = Column(Numeric(12, 2), nullable=False)
    scope_type = Column(String(16), nullable=False)
    scope_id = Column(Integer, nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL) OR (scope_type != 'GLOBAL' AND scope_id IS NOT NULL)",
            name="ck_buffer_rules_scope",
        ),
    )
