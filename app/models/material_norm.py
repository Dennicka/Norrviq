from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MaterialConsumptionNorm(Base):
    __tablename__ = "material_consumption_norms"

    id = Column(Integer, primary_key=True, index=True)
    active = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=True)
    material_name = Column(String(255), nullable=False)
    material_category = Column(String(100), nullable=False)
    applies_to_work_type = Column(String(100), nullable=False, index=True)
    work_kind = Column(String(100), nullable=True, index=True)
    basis_type = Column(String(30), nullable=True)
    quantity_per_basis = Column(Numeric(12, 4), nullable=True)
    basis_unit = Column(String(20), nullable=True)
    waste_factor_pct = Column(Numeric(6, 2), nullable=True)
    surface_type = Column(String(20), nullable=False, default="custom")
    consumption_value = Column(Numeric(12, 4), nullable=False)
    consumption_unit = Column(String(20), nullable=False, default="per_1_m2")
    material_unit = Column(String(20), nullable=False, default="pcs")
    package_size = Column(Numeric(12, 4), nullable=True)
    package_unit = Column(String(20), nullable=True)
    waste_percent = Column(Numeric(6, 2), nullable=False, default=10)
    coats_multiplier_mode = Column(String(20), nullable=False, default="none")
    brand_product = Column(String(255), nullable=True)
    default_unit_price_sek = Column(Numeric(12, 2), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
