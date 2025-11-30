from decimal import Decimal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.settings import get_or_create_settings

router = APIRouter(prefix="/settings", tags=["settings"])


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
    form_data = dict(form)
    if not form_data:
        body = (await request.body()).decode()
        form_data = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(body).items()}

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
