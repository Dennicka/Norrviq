from sqlalchemy import Boolean, CheckConstraint, Column, Integer, Numeric, String, Text

from app.db import Base


class MaterialCatalogItem(Base):
    __tablename__ = "material_catalog_items"
    __table_args__ = (
        CheckConstraint("package_size > 0", name="ck_material_catalog_package_size_gt_zero"),
        CheckConstraint("price_ex_vat >= 0", name="ck_material_catalog_price_non_negative"),
        CheckConstraint("vat_rate_pct >= 0 AND vat_rate_pct <= 100", name="ck_material_catalog_vat_range"),
    )

    id = Column(Integer, primary_key=True, index=True)
    material_code = Column(String(100), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    unit = Column(String(20), nullable=False)
    package_size = Column(Numeric(12, 4), nullable=False)
    package_unit = Column(String(20), nullable=False)
    price_ex_vat = Column(Numeric(12, 2), nullable=False)
    vat_rate_pct = Column(Numeric(5, 2), nullable=False, default=25)
    supplier_name = Column(String(255), nullable=True)
    supplier_sku = Column(String(100), nullable=True)
    brand = Column(String(100), nullable=True)
    variant = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_default_for_material = Column(Boolean, nullable=False, default=False)
