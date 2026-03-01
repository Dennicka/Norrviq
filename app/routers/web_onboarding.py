from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.models.company_profile import CompanyProfile
from app.models.pricing_policy import PricingPolicy
from app.models.terms_template import TermsTemplate
from app.models.worktype import WorkType
from app.services.setup_status import get_setup_status
from app.services.terms_templates import create_versioned_template
from app.scripts.seed_defaults import seed_defaults

router = APIRouter(tags=["onboarding"])

ONBOARDING_ORDER = ["overview", "company", "terms", "pricing", "pdf"]


def _next_block_step(checks) -> str | None:
    mapping = {
        "company_profile_present": "company",
        "terms_templates_present_sv": "terms",
        "pricing_policy_present": "pricing",
        "pdf_engine_ready": "pdf",
        "admin_user_exists": "overview",
        "worktypes_seeded": "overview",
    }
    for check in checks:
        if check.status == "BLOCK":
            return mapping.get(check.id, "overview")
    return None


@router.get("/onboarding")
async def onboarding_page(
    request: Request,
    step: str = "overview",
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    checks = get_setup_status(db)
    block_count = sum(1 for c in checks if c.status == "BLOCK")
    next_block_step = _next_block_step(checks)

    if step not in ONBOARDING_ORDER:
        step = "overview"

    context = template_context(request, lang)
    context.update(
        {
            "checks": checks,
            "step": step,
            "block_count": block_count,
            "next_block_step": next_block_step,
            "company": db.get(CompanyProfile, 1) or CompanyProfile(id=1),
            "has_sv_terms": any(c.id == "terms_templates_present_sv" and c.status == "OK" for c in checks),
            "pricing_policy": db.query(PricingPolicy).first(),
            "worktypes_missing": db.query(WorkType).count() == 0,
        }
    )

    if block_count == 0:
        return templates.TemplateResponse(request, "onboarding/complete.html", context)

    template_map = {
        "overview": "onboarding/overview.html",
        "company": "onboarding/company.html",
        "terms": "onboarding/terms.html",
        "pricing": "onboarding/pricing.html",
        "pdf": "onboarding/pdf.html",
    }
    return templates.TemplateResponse(request, template_map[step], context)


@router.post("/onboarding/company/save")
async def onboarding_save_company(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    legal_name = (form.get("legal_name") or "").strip()
    org_number = (form.get("org_number") or "").strip()

    if not legal_name:
        add_flash_message(request, "Company name is required.", "error")
        return RedirectResponse(url="/onboarding?step=company", status_code=status.HTTP_303_SEE_OTHER)

    profile = db.get(CompanyProfile, 1) or CompanyProfile(id=1)
    profile.legal_name = legal_name
    if org_number:
        profile.org_number = org_number
    db.add(profile)
    db.commit()
    add_flash_message(request, "Company profile saved.", "success")
    return RedirectResponse(url="/onboarding?step=overview", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/onboarding/terms/seed-default")
async def onboarding_seed_terms(request: Request, db: Session = Depends(get_db)):
    has_sv_terms = (
        db.query(TermsTemplate)
        .filter(TermsTemplate.is_active.is_(True), TermsTemplate.lang == "sv")
        .first()
        is not None
    )
    if not has_sv_terms:
        create_versioned_template(
            db,
            segment="B2C",
            doc_type="OFFER",
            lang="sv",
            title="Standardvillkor Offert",
            body_text="Standardvillkor för offert.",
            is_active=True,
        )
        create_versioned_template(
            db,
            segment="B2C",
            doc_type="INVOICE",
            lang="sv",
            title="Standardvillkor Faktura",
            body_text="Standardvillkor för faktura.",
            is_active=True,
        )
        db.commit()
    add_flash_message(request, "Default Swedish terms added.", "success")
    return RedirectResponse(url="/onboarding?step=overview", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/onboarding/pricing/save-default")
async def onboarding_save_pricing(request: Request, db: Session = Depends(get_db)):
    policy = db.query(PricingPolicy).first() or PricingPolicy()
    if policy.id is None:
        policy.min_margin_pct = Decimal("15.00")
        policy.min_profit_sek = Decimal("1000.00")
        policy.min_effective_hourly_ex_vat = Decimal("500.00")
        policy.block_issue_below_floor = True
        policy.warn_only_mode = False
        policy.min_completeness_score_for_fixed = 70
        policy.min_completeness_score_for_per_m2 = 60
        policy.min_completeness_score_for_per_room = 60
        policy.warn_only_below_score = False
    db.add(policy)
    db.commit()
    add_flash_message(request, "Pricing policy ready.", "success")
    return RedirectResponse(url="/onboarding?step=overview", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/onboarding/seed-defaults")
async def onboarding_seed_defaults(request: Request):
    seed_defaults()
    add_flash_message(request, "Базовые справочники заполнены.", "success")
    return RedirectResponse(url="/onboarding?step=overview", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/onboarding/complete")
async def onboarding_complete(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    checks = get_setup_status(db)
    context.update({"checks": checks, "block_count": sum(1 for c in checks if c.status == "BLOCK")})
    return templates.TemplateResponse(request, "onboarding/complete.html", context)
