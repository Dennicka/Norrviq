from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from app.db import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    invoice_number = Column(String, unique=True, index=True, nullable=True)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    paid_date = Column(Date, nullable=True)

    status = Column(String, nullable=False, default="draft")

    work_sum_without_moms = Column(Numeric(12, 2), nullable=False)
    moms_amount = Column(Numeric(12, 2), nullable=False)
    rot_amount = Column(Numeric(12, 2), nullable=False)
    client_pays_total = Column(Numeric(12, 2), nullable=False)

    comment = Column(String, nullable=True)
    invoice_terms_snapshot_title = Column(Text, nullable=True)
    invoice_terms_snapshot_body = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="invoices")
