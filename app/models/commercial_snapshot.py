from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, func

from app.db import Base


class CommercialSnapshot(Base):
    __tablename__ = "commercial_snapshots"
    __table_args__ = (UniqueConstraint("doc_type", "doc_id", name="uq_commercial_snapshots_doc"),)

    id = Column(Integer, primary_key=True, index=True)
    doc_type = Column(String(20), nullable=False)  # OFFER | INVOICE
    doc_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    mode = Column(String(20), nullable=False)
    segment = Column(String(20), nullable=False)
    currency = Column(String(8), nullable=False, default="SEK")
    m2_basis = Column(String(32), nullable=True)

    units_json = Column(Text, nullable=False)
    rates_json = Column(Text, nullable=False)
    totals_json = Column(Text, nullable=False)
    line_items_json = Column(Text, nullable=False)
