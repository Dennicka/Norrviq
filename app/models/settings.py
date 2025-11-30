from sqlalchemy import Column, Integer, Numeric
from sqlalchemy.orm import Session

from app.db import Base


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    hourly_rate_company = Column(Numeric(10, 2), nullable=False, default=550.00)
    default_worker_hourly_rate = Column(Numeric(10, 2), nullable=False, default=180.00)
    employer_contributions_percent = Column(Numeric(5, 2), nullable=False, default=31.42)
    moms_percent = Column(Numeric(5, 2), nullable=False, default=25.00)
    rot_percent = Column(Numeric(5, 2), nullable=False, default=50.00)
    fuel_price_per_liter = Column(Numeric(10, 2), nullable=False, default=20.00)
    transport_cost_per_km = Column(Numeric(10, 2), nullable=False, default=25.00)
    default_overhead_percent = Column(Numeric(5, 2), nullable=False, default=10.00)
    default_worker_tax_percent_for_net = Column(Numeric(5, 2), nullable=False, default=30.00)


def get_or_create_settings(db: Session) -> "Settings":
    settings = db.query(Settings).first()
    if settings is None:
        settings = Settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
