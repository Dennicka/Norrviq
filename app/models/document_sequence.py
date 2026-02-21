from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func

from app.db import Base


class DocumentSequence(Base):
    __tablename__ = "document_sequences"
    __table_args__ = (UniqueConstraint("doc_type", "year", name="uq_document_sequences_type_year"),)

    id = Column(Integer, primary_key=True, index=True)
    doc_type = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    next_number = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
