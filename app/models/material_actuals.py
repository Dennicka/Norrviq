from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class MaterialPurchase(Base):
    __tablename__ = "material_purchases"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_material_purchase_project_idempotency"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    purchased_at = Column(DateTime, nullable=False, server_default=func.now())
    invoice_ref = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    currency = Column(String(10), nullable=False, default="SEK")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    lines = relationship("MaterialPurchaseLine", back_populates="purchase", cascade="all, delete-orphan")


class MaterialPurchaseLine(Base):
    __tablename__ = "material_purchase_lines"
    __table_args__ = (
        CheckConstraint("packs_count > 0", name="ck_purchase_lines_packs_count_gt_zero"),
        CheckConstraint("pack_size > 0", name="ck_purchase_lines_pack_size_gt_zero"),
        CheckConstraint("pack_price_ex_vat >= 0", name="ck_purchase_lines_pack_price_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("material_purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False, index=True)
    packs_count = Column(Numeric(12, 2), nullable=False)
    pack_size = Column(Numeric(12, 2), nullable=False)
    unit = Column(String(20), nullable=False)
    pack_price_ex_vat = Column(Numeric(12, 2), nullable=False)
    vat_rate_pct = Column(Numeric(5, 2), nullable=False, default=25)
    line_cost_ex_vat = Column(Numeric(12, 2), nullable=False)
    line_cost_inc_vat = Column(Numeric(12, 2), nullable=False)
    source = Column(String(20), nullable=False, default="MANUAL")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    purchase = relationship("MaterialPurchase", back_populates="lines")
    material = relationship("Material")


class ProjectMaterialActuals(Base):
    __tablename__ = "project_material_actuals"

    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    actual_cost_ex_vat = Column(Numeric(12, 2), nullable=False, default=0)
    actual_cost_inc_vat = Column(Numeric(12, 2), nullable=False, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ProjectMaterialStock(Base):
    __tablename__ = "project_material_stock"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    qty_in_base_unit = Column(Numeric(12, 2), nullable=False, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "material_id", name="uq_project_material_stock_project_material"),)
