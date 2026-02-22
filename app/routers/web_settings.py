from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.audit import log_event
from app.models.buffer_rule import BufferRule
from app.models.material_recipe import MaterialRecipe
from app.models.company_profile import get_or_create_company_profile
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.settings import get_or_create_settings
from app.models.terms_template import TermsTemplate
from app.models.speed_profile import SpeedProfile
from app.models.paint_system import PaintSystem, PaintSystemStep, PaintSystemSurface
from app.models.sanity_rule import SanityRule
from app.services.terms_templates import create_versioned_template

router = APIRouter(prefix="/settings", tags=["settings"])

SEGMENTS = ("B2C", "BRF", "B2B")
DOC_TYPES = ("OFFER", "INVOICE")
LANGS = ("sv", "ru", "en")


def _load_form_data(form) -> dict:
    return dict(form)


def _audit(request: Request, db: Session, *, event_type: str, entity_type: str, entity_id: int | str | None, details: dict, severity: str = "INFO") -> None:
    log_event(
        db,
        request,
        event_type,
        entity_type=entity_type.upper(),
        entity_id=entity_id,
        severity=severity,
        metadata=details,
    )


@router.get("/")
async def settings_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    settings_obj = get_or_create_settings(db)
    context = template_context(request, lang)
    context["settings_obj"] = settings_obj
    return templates.TemplateResponse(request, "settings/form.html", context)


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


@router.get("/pricing-policy")
async def pricing_policy_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    policy = get_or_create_pricing_policy(db)
    context = template_context(request, lang)
    context.update({"policy": policy, "errors": {}, "form_data": {}})
    return templates.TemplateResponse(request, "settings/pricing_policy.html", context)


@router.post("/pricing-policy")
async def update_pricing_policy(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    policy = get_or_create_pricing_policy(db)
    form = await request.form()
    data = _load_form_data(form)

    errors: dict[str, str] = {}

    def _decimal_field(field: str):
        raw = (data.get(field) or "").strip()
        try:
            return Decimal(raw)
        except Exception:
            errors[field] = "Некорректное число"
            return None

    min_margin_pct = _decimal_field("min_margin_pct")
    min_profit_sek = _decimal_field("min_profit_sek")
    min_effective_hourly_ex_vat = _decimal_field("min_effective_hourly_ex_vat")

    def _int_field(field: str, *, min_value: int = 0, max_value: int = 100):
        raw = (data.get(field) or "").strip()
        try:
            value = int(raw)
        except Exception:
            errors[field] = "Некорректное целое число"
            return None
        if value < min_value or value > max_value:
            errors[field] = f"Значение должно быть в диапазоне {min_value}–{max_value}"
            return None
        return value

    min_completeness_score_for_fixed = _int_field("min_completeness_score_for_fixed")
    min_completeness_score_for_per_m2 = _int_field("min_completeness_score_for_per_m2")
    min_completeness_score_for_per_room = _int_field("min_completeness_score_for_per_room")

    if min_margin_pct is not None and (min_margin_pct < 0 or min_margin_pct > 80):
        errors["min_margin_pct"] = "Маржа должна быть в диапазоне 0–80%"
    if min_profit_sek is not None and min_profit_sek < 0:
        errors["min_profit_sek"] = "Минимальная прибыль должна быть >= 0"
    if min_effective_hourly_ex_vat is not None and min_effective_hourly_ex_vat <= 0:
        errors["min_effective_hourly_ex_vat"] = "Ставка должна быть больше 0"

    if errors:
        context = template_context(request, lang)
        context.update({"policy": policy, "errors": errors, "form_data": data})
        return templates.TemplateResponse(request, "settings/pricing_policy.html", context, status_code=400)

    policy.min_margin_pct = min_margin_pct.quantize(Decimal("0.01"))
    policy.min_profit_sek = min_profit_sek.quantize(Decimal("0.01"))
    policy.min_effective_hourly_ex_vat = min_effective_hourly_ex_vat.quantize(Decimal("0.01"))
    policy.block_issue_below_floor = data.get("block_issue_below_floor") in ("on", "true", "1", True, 1)
    policy.warn_only_mode = data.get("warn_only_mode") in ("on", "true", "1", True, 1)
    policy.min_completeness_score_for_fixed = min_completeness_score_for_fixed
    policy.min_completeness_score_for_per_m2 = min_completeness_score_for_per_m2
    policy.min_completeness_score_for_per_room = min_completeness_score_for_per_room
    policy.warn_only_below_score = data.get("warn_only_below_score") in ("on", "true", "1", True, 1)

    _audit(
        request,
        db,
        event_type="policy_updated",
        entity_type="pricing_policy",
        entity_id=policy.id,
        details={
            "min_margin_pct": str(policy.min_margin_pct),
            "min_profit_sek": str(policy.min_profit_sek),
            "min_effective_hourly_ex_vat": str(policy.min_effective_hourly_ex_vat),
            "block_issue_below_floor": policy.block_issue_below_floor,
            "warn_only_mode": policy.warn_only_mode,
            "min_completeness_score_for_fixed": policy.min_completeness_score_for_fixed,
            "min_completeness_score_for_per_m2": policy.min_completeness_score_for_per_m2,
            "min_completeness_score_for_per_room": policy.min_completeness_score_for_per_room,
            "warn_only_below_score": policy.warn_only_below_score,
        },
    )
    db.add(policy)
    db.commit()
    return RedirectResponse(url="/settings/pricing-policy", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/paint-systems")
async def paint_systems_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    systems = db.query(PaintSystem).order_by(PaintSystem.name.asc(), PaintSystem.version.desc()).all()
    recipes = db.query(MaterialRecipe).filter(MaterialRecipe.is_active.is_(True)).order_by(MaterialRecipe.name.asc()).all()
    context = template_context(request, lang)
    context.update({"systems": systems, "recipes": recipes, "surfaces": list(PaintSystemSurface)})
    return templates.TemplateResponse(request, "settings/paint_systems.html", context)


@router.post("/paint-systems/create")
async def paint_systems_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    system = PaintSystem(
        name=(form.get("name") or "").strip(),
        description=(form.get("description") or "").strip() or None,
        version=1,
        is_active=form.get("is_active") in ("on", "true", "1", True, 1),
    )
    db.add(system)
    db.commit()
    return RedirectResponse(url="/settings/paint-systems", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/paint-systems/{system_id}/steps")
async def paint_systems_add_step(system_id: int, request: Request, db: Session = Depends(get_db)):
    system = db.get(PaintSystem, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="Paint system not found")
    form = await request.form()
    recipe_id = int(form.get("recipe_id"))
    target_surface = form.get("target_surface")
    next_order = (max([s.step_order for s in system.steps], default=0) + 1)
    step = PaintSystemStep(
        paint_system_id=system.id,
        step_order=next_order,
        target_surface=PaintSystemSurface(target_surface),
        recipe_id=recipe_id,
        override_coats_count=int(form.get("override_coats_count")) if form.get("override_coats_count") else None,
        override_waste_pct=Decimal(str(form.get("override_waste_pct"))) if form.get("override_waste_pct") else None,
        is_optional=form.get("is_optional") in ("on", "true", "1", True, 1),
    )
    db.add(step)
    db.commit()
    return RedirectResponse(url="/settings/paint-systems", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/paint-systems/{system_id}/version")
async def paint_systems_version(system_id: int, db: Session = Depends(get_db)):
    system = db.get(PaintSystem, system_id)
    if not system:
        raise HTTPException(status_code=404, detail="Paint system not found")
    next_version = db.query(PaintSystem).filter(PaintSystem.name == system.name).order_by(PaintSystem.version.desc()).first()
    new_system = PaintSystem(name=system.name, description=system.description, is_active=True, version=(next_version.version + 1 if next_version else system.version + 1))
    db.add(new_system)
    db.flush()
    for step in sorted(system.steps, key=lambda x: x.step_order):
        db.add(PaintSystemStep(
            paint_system_id=new_system.id,
            step_order=step.step_order,
            target_surface=step.target_surface,
            recipe_id=step.recipe_id,
            override_coats_count=step.override_coats_count,
            override_waste_pct=step.override_waste_pct,
            is_optional=step.is_optional,
        ))
    system.is_active = False
    db.add(system)
    db.commit()
    return RedirectResponse(url="/settings/paint-systems", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/company")
async def company_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    profile = get_or_create_company_profile(db)
    context = template_context(request, lang)
    templates_list = db.query(TermsTemplate).filter(TermsTemplate.is_active.is_(True)).order_by(TermsTemplate.id.desc()).all()
    context.update({"company": profile, "errors": [], "terms_templates": templates_list})
    return templates.TemplateResponse(request, "settings/company_form.html", context)


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
        templates_list = db.query(TermsTemplate).filter(TermsTemplate.is_active.is_(True)).order_by(TermsTemplate.id.desc()).all()
        context.update({"company": profile, "errors": errors, "form_data": data, "terms_templates": templates_list})
        return templates.TemplateResponse(request, "settings/company_form.html", context, status_code=400)

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

    def _to_int(v: str | None) -> int | None:
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    profile.default_offer_terms_template_id = _to_int(data.get("default_offer_terms_template_id"))
    profile.default_invoice_terms_template_id = _to_int(data.get("default_invoice_terms_template_id"))

    _audit(
        request,
        db,
        event_type="company_defaults_updated",
        entity_type="company_profile",
        entity_id=profile.id,
        details={
            "default_offer_terms_template_id": profile.default_offer_terms_template_id,
            "default_invoice_terms_template_id": profile.default_invoice_terms_template_id,
        },
    )
    db.add(profile)
    db.commit()

    return RedirectResponse(url="/settings/company", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/terms")
async def terms_templates_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    templates_list = db.query(TermsTemplate).order_by(TermsTemplate.created_at.desc()).all()
    context.update({"terms_templates": templates_list, "segments": SEGMENTS, "doc_types": DOC_TYPES, "langs": LANGS})
    return templates.TemplateResponse(request, "settings/terms_templates.html", context)


@router.post("/terms")
async def create_terms_template(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    segment = (form.get("segment") or "B2C").strip().upper()
    doc_type = (form.get("doc_type") or "OFFER").strip().upper()
    lang = (form.get("lang") or "sv").strip().lower()
    source_template_id = form.get("source_template_id")

    title = (form.get("title") or "").strip()
    body_text = (form.get("body_text") or "").strip()

    if source_template_id:
        source = db.get(TermsTemplate, int(source_template_id))
        if source:
            segment = source.segment
            doc_type = source.doc_type
            lang = source.lang
            title = title or source.title
            body_text = body_text or source.body_text

    template = create_versioned_template(
        db,
        segment=segment,
        doc_type=doc_type,
        lang=lang,
        title=title or "Terms",
        body_text=body_text or "",
        is_active=bool(form.get("is_active", "1")),
    )
    _audit(
        request,
        db,
        event_type="terms_template_versioned" if source_template_id else "terms_template_created",
        entity_type="terms_template",
        entity_id=template.id,
        details={"segment": template.segment, "doc_type": template.doc_type, "lang": template.lang, "version": template.version},
    )
    db.commit()
    return RedirectResponse(url="/settings/terms", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/buffers")
async def buffers_settings_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    rules = db.query(BufferRule).order_by(BufferRule.scope_type.asc(), BufferRule.priority.desc(), BufferRule.id.desc()).all()
    context = template_context(request, lang)
    context.update({"rules": rules})
    return templates.TemplateResponse(request, "settings/buffers.html", context)


@router.post("/buffers")
async def upsert_buffer_rule(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = _load_form_data(form)
    rule_id = data.get("rule_id")
    action = data.get("action") or "save"

    rule = db.get(BufferRule, int(rule_id)) if rule_id else BufferRule()
    if action == "deactivate" and rule is not None:
        rule.is_active = False
        event_type = "buffer_rule_deactivated"
    else:
        rule.kind = (data.get("kind") or "SETUP").upper()
        rule.basis = (data.get("basis") or "LABOR_HOURS").upper()
        rule.unit = (data.get("unit") or "PERCENT").upper()
        rule.value = Decimal((data.get("value") or "0").strip() or "0").quantize(Decimal("0.01"))
        rule.scope_type = (data.get("scope_type") or "GLOBAL").upper()
        scope_id_raw = (data.get("scope_id") or "").strip()
        rule.scope_id = int(scope_id_raw) if scope_id_raw else None
        rule.priority = int((data.get("priority") or "0").strip() or "0")
        rule.is_active = data.get("is_active") in ("on", "true", "1", True, 1)
        if rule.scope_type == "GLOBAL":
            rule.scope_id = None
        event_type = "buffer_rule_updated" if rule_id else "buffer_rule_created"

    db.add(rule)
    _audit(
        request,
        db,
        event_type=event_type,
        entity_type="buffer_rule",
        entity_id=rule.id or 0,
        details={
            "kind": getattr(rule, "kind", None),
            "basis": getattr(rule, "basis", None),
            "scope_type": getattr(rule, "scope_type", None),
            "scope_id": getattr(rule, "scope_id", None),
            "priority": getattr(rule, "priority", None),
            "is_active": getattr(rule, "is_active", None),
        },
    )
    db.commit()
    return RedirectResponse(url="/settings/buffers", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/speed-profiles")
async def speed_profiles_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    profiles = db.query(SpeedProfile).order_by(SpeedProfile.code.asc()).all()
    context = template_context(request, lang)
    context.update({"profiles": profiles})
    return templates.TemplateResponse(request, "settings/speed_profiles.html", context)


@router.post("/speed-profiles")
async def upsert_speed_profile(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = _load_form_data(form)
    profile_id = data.get("profile_id")
    profile = db.get(SpeedProfile, int(profile_id)) if profile_id else SpeedProfile()

    profile.code = (data.get("code") or profile.code or "CUSTOM").strip().upper()
    profile.name_ru = (data.get("name_ru") or profile.name_ru or profile.code or "").strip()
    profile.name_sv = (data.get("name_sv") or profile.name_sv or profile.code or "").strip()
    profile.multiplier = Decimal((data.get("multiplier") or profile.multiplier or "1.000")).quantize(Decimal("0.001"))
    profile.is_active = data.get("is_active") in ("on", "true", "1", True, 1)

    db.add(profile)
    _audit(
        request,
        db,
        event_type="speed_profile_updated" if profile_id else "speed_profile_created",
        entity_type="speed_profile",
        entity_id=profile.id or 0,
        details={"code": profile.code, "multiplier": str(profile.multiplier), "is_active": profile.is_active},
    )
    db.commit()
    return RedirectResponse(url="/settings/speed-profiles", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/sanity-rules")
async def sanity_rules_page(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    rules = db.query(SanityRule).order_by(SanityRule.entity.asc(), SanityRule.field.asc(), SanityRule.id.asc()).all()
    context = template_context(request, lang)
    context.update({"rules": rules})
    return templates.TemplateResponse(request, "settings/sanity_rules.html", context)


@router.post("/sanity-rules/{rule_id}")
async def update_sanity_rule(rule_id: int, request: Request, db: Session = Depends(get_db)):
    rule = db.get(SanityRule, rule_id)
    if not rule:
        return RedirectResponse(url="/settings/sanity-rules", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    rule.is_active = form.get("is_active") in ("on", "1", "true", True, 1)
    severity = (form.get("severity") or rule.severity).upper()
    if severity in ("WARNING", "BLOCK"):
        rule.severity = severity
    if form.get("min_value") not in (None, ""):
        rule.min_value = Decimal(form.get("min_value"))
    if form.get("max_value") not in (None, ""):
        rule.max_value = Decimal(form.get("max_value"))
    if form.get("message_ru") is not None:
        rule.message_ru = (form.get("message_ru") or "").strip() or rule.message_ru
    if form.get("message_sv") is not None:
        rule.message_sv = (form.get("message_sv") or "").strip() or rule.message_sv

    _audit(
        request,
        db,
        event_type="sanity_rule_updated",
        entity_type="sanity_rule",
        entity_id=rule.id,
        details={"severity": rule.severity, "is_active": rule.is_active},
    )
    db.add(rule)
    db.commit()
    return RedirectResponse(url="/settings/sanity-rules", status_code=status.HTTP_303_SEE_OTHER)
