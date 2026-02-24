from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import relationship

from app.db import Base


class ProjectPricing(Base):
    __tablename__ = "project_pricing"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    mode = Column(String(32), nullable=False, default="HOURLY")

    hourly_rate_override = Column(Numeric(12, 2), nullable=True)
    fixed_total_price = Column(Numeric(12, 2), nullable=True)
    rate_per_m2 = Column(Numeric(12, 2), nullable=True)
    rate_per_room = Column(Numeric(12, 2), nullable=True)
    rate_per_piece = Column(Numeric(12, 2), nullable=True)
    target_margin_pct = Column(Numeric(5, 2), nullable=True)

    include_materials = Column(Boolean, nullable=False, default=True)
    include_travel_setup_buffers = Column(Boolean, nullable=False, default=True)
    currency = Column(String(3), nullable=False, default="SEK")
    pricing_mode = Column(String(16), nullable=False, default="hourly")
    hourly_rate = Column(Numeric(12, 2), nullable=False, default=0)
    sqm_rate = Column(Numeric(12, 2), nullable=False, default=0)
    sqm_basis = Column(String(32), nullable=False, default="walls_ceilings")
    sqm_custom_value = Column(Numeric(12, 2), nullable=True)
    fixed_price_amount = Column(Numeric(12, 2), nullable=False, default=0)
    include_materials_in_sell_price = Column(Boolean, nullable=False, default=True)
    markup_percent = Column(Numeric(8, 2), nullable=False, default=0)
    rounding_mode = Column(String(16), nullable=False, default="none")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="pricing")
