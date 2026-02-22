from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, func
from sqlalchemy.orm import Session

from app.db import Base


class PricingPolicy(Base):
    __tablename__ = "pricing_policy"

    id = Column(Integer, primary_key=True, index=True)
    min_margin_pct = Column(Numeric(5, 2), nullable=False, default=15.00)
    min_profit_sek = Column(Numeric(12, 2), nullable=False, default=1000.00)
    min_effective_hourly_ex_vat = Column(Numeric(12, 2), nullable=False, default=500.00)
    block_issue_below_floor = Column(Boolean, nullable=False, default=True)
    warn_only_mode = Column(Boolean, nullable=False, default=False)
    min_completeness_score_for_fixed = Column(Integer, nullable=False, default=70)
    min_completeness_score_for_per_m2 = Column(Integer, nullable=False, default=60)
    min_completeness_score_for_per_room = Column(Integer, nullable=False, default=60)
    warn_only_below_score = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


def get_or_create_pricing_policy(db: Session) -> "PricingPolicy":
    policy = db.query(PricingPolicy).first()
    if policy is None:
        policy = PricingPolicy()
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy
