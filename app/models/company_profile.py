from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import Session

from app.db import Base


class CompanyProfile(Base):
    __tablename__ = "company_profile"

    id = Column(Integer, primary_key=True, default=1)
    legal_name = Column(String(255), nullable=False, default="Trenor Måleri AB")
    org_number = Column(String(64), nullable=False, default="")
    vat_number = Column(String(64), nullable=True)
    address_line1 = Column(String(255), nullable=False, default="")
    address_line2 = Column(String(255), nullable=True)
    postal_code = Column(String(32), nullable=False, default="")
    city = Column(String(128), nullable=False, default="")
    country = Column(String(128), nullable=False, default="Sverige")
    email = Column(String(255), nullable=False, default="")
    phone = Column(String(64), nullable=True)
    website = Column(String(255), nullable=True)

    bankgiro = Column(String(64), nullable=True)
    plusgiro = Column(String(64), nullable=True)
    iban = Column(String(64), nullable=True)
    bic = Column(String(64), nullable=True)

    payment_terms_days = Column(Integer, nullable=False, default=10)
    invoice_prefix = Column(String(16), nullable=False, default="TR-")
    offer_prefix = Column(String(16), nullable=False, default="OF-")
    document_number_padding = Column(Integer, nullable=False, default=4)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def has_any_payment_method(self) -> bool:
        return bool((self.bankgiro or "").strip() or (self.plusgiro or "").strip() or (self.iban or "").strip())

    def is_document_ready(self) -> bool:
        required_text = [
            self.legal_name,
            self.org_number,
            self.address_line1,
            self.postal_code,
            self.city,
            self.country,
            self.email,
        ]
        return all((value or "").strip() for value in required_text) and self.has_any_payment_method()


def get_or_create_company_profile(db: Session) -> CompanyProfile:
    profile = db.get(CompanyProfile, 1)
    if profile is None:
        profile = CompanyProfile(id=1)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile
