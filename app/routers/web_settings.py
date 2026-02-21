from decimal import Decimal
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.company_profile import get_or_create_company_profile
from app.models.settings import get_or_create_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _load_form_data(form) -> dict:
    return dict(form)


@router.get("/")
async def settings_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    settings_obj = get_or_create_settings(db)
    context = template_context(request, lang)
    context["settings_obj"] = settings_obj
    return templates.TemplateResponse("settings/form.html", context)


@router.post("/")
async def update_settings(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    settings_obj = get_or_create_settings(db)
    form = await request.form()
    form_data = _load_form_data(form)

    settings_obj.hourly_rate_company = Decimal(form_data.get("hourly_rate_company") or settings_obj.hourly_rate_company)
    settings_obj.default_worker_hourly_rate = Decimal(
        form_data.get("default_worker_hourly_rate") or settings_obj.default_worker_hourly_rate
    )
    settings_obj.employer_contributions_percent = Decimal(
        form_data.get("employer_contributions_percent") or settings_obj.employer_contributions_percent
    )
    settings_obj.moms_percent = Decimal(form_data.get("moms_percent") or settings_obj.moms_percent)
    settings_obj.rot_percent = Decimal(form_data.get("rot_percent") or settings_obj.rot_percent)
    settings_obj.fuel_price_per_liter = Decimal(form_data.get("fuel_price_per_liter") or settings_obj.fuel_price_per_liter)
    settings_obj.transport_cost_per_km = Decimal(
        form_data.get("transport_cost_per_km") or settings_obj.transport_cost_per_km
    )
    settings_obj.default_overhead_percent = Decimal(
        form_data.get("default_overhead_percent") or settings_obj.default_overhead_percent
    )
    settings_obj.default_worker_tax_percent_for_net = Decimal(
        form_data.get("default_worker_tax_percent_for_net") or settings_obj.default_worker_tax_percent_for_net
    )

    db.add(settings_obj)
    db.commit()
    db.refresh(settings_obj)

    return RedirectResponse(url="/settings/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/company")
async def company_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    profile = get_or_create_company_profile(db)
    context = template_context(request, lang)
    context.update({"company": profile, "errors": []})
    return templates.TemplateResponse("settings/company_form.html", context)


@router.post("/company")
async def update_company(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    profile = get_or_create_company_profile(db)
    form = await request.form()
    data = _load_form_data(form)

    errors: list[str] = []
    org_number = (data.get("org_number") or "").replace("-", "").strip()
    if not org_number.isdigit() or len(org_number) not in (10, 12):
        errors.append("company.validation.org_number")

    vat_number = (data.get("vat_number") or "").strip()
    if vat_number and (len(vat_number) < 8 or not any(ch.isdigit() for ch in vat_number)):
        errors.append("company.validation.vat_number")

    email = (data.get("email") or "").strip()
    if "@" not in email or "." not in email:
        errors.append("company.validation.email")

    payment_terms_days_raw = (data.get("payment_terms_days") or "10").strip()
    try:
        payment_terms_days = int(payment_terms_days_raw)
        if payment_terms_days <= 0:
            errors.append("company.validation.payment_terms_days")
    except ValueError:
        errors.append("company.validation.payment_terms_days")
        payment_terms_days = profile.payment_terms_days

    bankgiro = (data.get("bankgiro") or "").strip()
    plusgiro = (data.get("plusgiro") or "").strip()
    iban = (data.get("iban") or "").strip()
    if not (bankgiro or plusgiro or iban):
        errors.append("company.validation.payment_method")

    padding_raw = (data.get("document_number_padding") or "4").strip()
    try:
        document_number_padding = int(padding_raw)
        if document_number_padding < 2 or document_number_padding > 8:
            errors.append("company.validation.document_number_padding")
    except ValueError:
        errors.append("company.validation.document_number_padding")
        document_number_padding = profile.document_number_padding

    if errors:
        context = template_context(request, lang)
        context.update({"company": profile, "errors": errors, "form_data": data})
        return templates.TemplateResponse("settings/company_form.html", context, status_code=400)

    profile.legal_name = (data.get("legal_name") or "").strip()
    profile.org_number = org_number
    profile.vat_number = vat_number or None
    profile.address_line1 = (data.get("address_line1") or "").strip()
    profile.address_line2 = (data.get("address_line2") or "").strip() or None
    profile.postal_code = (data.get("postal_code") or "").strip()
    profile.city = (data.get("city") or "").strip()
    profile.country = (data.get("country") or "").strip()
    profile.email = email
    profile.phone = (data.get("phone") or "").strip() or None
    profile.website = (data.get("website") or "").strip() or None
    profile.bankgiro = bankgiro or None
    profile.plusgiro = plusgiro or None
    profile.iban = iban or None
    profile.bic = (data.get("bic") or "").strip() or None
    profile.payment_terms_days = payment_terms_days
    profile.invoice_prefix = (data.get("invoice_prefix") or "TR-").strip() or "TR-"
    profile.offer_prefix = (data.get("offer_prefix") or "OF-").strip() or "OF-"
    profile.document_number_padding = document_number_padding

    db.add(profile)
    db.commit()

    return RedirectResponse(url="/settings/company", status_code=status.HTTP_303_SEE_OTHER)
