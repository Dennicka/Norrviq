from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import relationship

from app.db import Base


class RotCase(Base):
    __tablename__ = "rot_cases"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    eligible_labor_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    rot_pct = Column(Numeric(5, 2), nullable=False, default=30)
    rot_amount = Column(Numeric(12, 2), nullable=False, default=0)
    customer_personnummer = Column(Text, nullable=True)
    property_identifier = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    invoice = relationship("Invoice", back_populates="rot_case")
