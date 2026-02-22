from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from app.db import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    source_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    invoice_number = Column(String, unique=True, index=True, nullable=True)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    paid_date = Column(Date, nullable=True)

    status = Column(String, nullable=False, default="draft")

    work_sum_without_moms = Column(Numeric(12, 2), nullable=False)
    moms_amount = Column(Numeric(12, 2), nullable=False)
    rot_amount = Column(Numeric(12, 2), nullable=False)
    client_pays_total = Column(Numeric(12, 2), nullable=False)

    subtotal_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    labour_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    material_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    other_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    vat_total = Column(Numeric(12, 2), nullable=False, default=0)
    total_inc_vat = Column(Numeric(12, 2), nullable=False, default=0)

    rot_snapshot_enabled = Column(Boolean, nullable=False, default=False)
    rot_snapshot_pct = Column(Numeric(5, 2), nullable=False, default=0)
    rot_snapshot_eligible_labor_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    rot_snapshot_amount = Column(Numeric(12, 2), nullable=False, default=0)

    commercial_mode_snapshot = Column(String(20), nullable=True)
    units_snapshot = Column(Text, nullable=True)
    rates_snapshot = Column(Text, nullable=True)
    subtotal_ex_vat_snapshot = Column(Numeric(12, 2), nullable=True)
    vat_total_snapshot = Column(Numeric(12, 2), nullable=True)
    total_inc_vat_snapshot = Column(Numeric(12, 2), nullable=True)
    material_pricing_snapshot = Column(Text, nullable=True)
    material_source_snapshot_hash = Column(String(64), nullable=True)

    comment = Column(String, nullable=True)
    invoice_terms_snapshot_title = Column(Text, nullable=True)
    invoice_terms_snapshot_body = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="invoices", foreign_keys=[project_id])
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.position")
    rot_case = relationship("RotCase", back_populates="invoice", uselist=False, cascade="all, delete-orphan")
