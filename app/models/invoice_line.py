from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "position", name="uq_invoice_lines_invoice_position"),
    )

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    kind = Column(String(20), nullable=False, default="OTHER")
    description = Column(Text, nullable=False)
    unit = Column(String(20), nullable=True)
    quantity = Column(Numeric(12, 2), nullable=False, default=1)
    unit_price_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    line_total_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    vat_rate_pct = Column(Numeric(5, 2), nullable=False, default=25)
    vat_amount = Column(Numeric(12, 2), nullable=False, default=0)
    line_total_inc_vat = Column(Numeric(12, 2), nullable=False, default=0)
    source_type = Column(String(20), nullable=True)
    source_id = Column(Integer, nullable=True)
    source_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    invoice = relationship("Invoice", back_populates="lines")
