from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db import Base


class SupplierMaterialPrice(Base):
    __tablename__ = "supplier_material_prices"
    __table_args__ = (
        UniqueConstraint("supplier_id", "material_id", "pack_size", name="uq_supplier_material_pack"),
    )

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_size = Column(Numeric(12, 2), nullable=False)
    pack_unit = Column(String(20), nullable=False)
    pack_price_ex_vat = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False, default="SEK")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    supplier = relationship("Supplier", back_populates="material_prices")
    material = relationship("Material", back_populates="supplier_prices")
