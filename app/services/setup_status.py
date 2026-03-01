from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.pricing_policy import PricingPolicy
from app.models.terms_template import TermsTemplate
from app.models.user import User
from app.services.pdf_renderer import invoice_pdf_capability


SetupState = Literal["OK", "WARN", "BLOCK"]


@dataclass(frozen=True)
class SetupCheck:
    id: str
    status: SetupState
    title: str
    details: str
    fix_url: str | None


def get_setup_status(db: Session) -> list[SetupCheck]:
    checks: list[SetupCheck] = []

    company = db.get(CompanyProfile, 1)
    company_name = (company.legal_name or "").strip() if company else ""
    company_ok = bool(company and company_name)
    checks.append(
        SetupCheck(
            id="company_profile_present",
            status="OK" if company_ok else "BLOCK",
            title="Company profile",
            details="Company name is required before issuing real documents.",
            fix_url="/onboarding?step=company",
        )
    )

    has_sv_terms = (
        db.query(func.count(TermsTemplate.id))
        .filter(TermsTemplate.is_active.is_(True), TermsTemplate.lang == "sv")
        .scalar()
        or 0
    ) > 0
    checks.append(
        SetupCheck(
            id="terms_templates_present_sv",
            status="OK" if has_sv_terms else "BLOCK",
            title="Swedish terms template",
            details="At least one active Swedish terms template must exist.",
            fix_url="/onboarding?step=terms",
        )
    )

    has_pricing_policy = (db.query(func.count(PricingPolicy.id)).scalar() or 0) > 0
    checks.append(
        SetupCheck(
            id="pricing_policy_present",
            status="OK" if has_pricing_policy else "WARN",
            title="Pricing policy",
            details="Pricing policy is recommended to reduce issue-time warnings.",
            fix_url="/onboarding?step=pricing",
        )
    )

    pdf_capability = invoice_pdf_capability()
    pdf_ready = pdf_capability.get("active_engine") != "fallback_pdf"
    checks.append(
        SetupCheck(
            id="pdf_engine_ready",
            status="OK" if pdf_ready else "WARN",
            title="PDF engine",
            details="Fallback PDF is active. Install WeasyPrint/Chromium for production output.",
            fix_url="/onboarding?step=pdf",
        )
    )

    has_users = (db.query(func.count(User.id)).scalar() or 0) > 0
    checks.append(
        SetupCheck(
            id="admin_user_exists",
            status="OK" if has_users else "WARN",
            title="User accounts",
            details="Create at least one admin/operator account.",
            fix_url="/admin/users",
        )
    )

    return checks


def get_blocking_setup_checks(db: Session) -> list[SetupCheck]:
    return [check for check in get_setup_status(db) if check.status == "BLOCK"]
