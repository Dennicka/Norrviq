from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material import Material
from app.models.material_norm import MaterialConsumptionNorm

router = APIRouter(prefix="/materials", tags=["materials"])

VALID_BASIS_TYPES = {"floor_area", "wall_area", "ceiling_area", "walls_plus_ceilings", "perimeter", "room_count", "custom"}
VALID_WORK_KINDS = {"paint_ceiling", "paint_walls", "putty_walls", "primer_walls", "cover_floor", "painting_ceiling", "painting_walls", "floor_covering"}
VALID_UNITS = {"l", "kg", "m2", "pcs", "roll", "bucket"}


def _to_decimal(raw: str | None, *, field: str, allow_empty: bool = False) -> Decimal | None:
    if raw in (None, ""):
        if allow_empty:
            return None
        raise ValueError(f"{field}:required")
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError):
        raise ValueError(f"{field}:invalid") from None
    return value


def _parse_rule_form(form) -> tuple[dict, list[str]]:
    errors: list[str] = []
    payload: dict = {}
    payload["is_active"] = form.get("is_active") in ("on", "true", "1", True, 1)
    payload["active"] = payload["is_active"]
    payload["name"] = (form.get("name") or "").strip()
    payload["material_name"] = (form.get("material_name") or "").strip()
    payload["material_catalog_item_id"] = form.get("material_catalog_item_id") or None
    payload["material_category"] = (form.get("material_category") or "other").strip()
    payload["work_kind"] = (form.get("work_kind") or "").strip().lower()
    payload["work_type_code"] = payload["work_kind"]
    payload["basis_type"] = (form.get("basis_type") or "").strip().lower()
    payload["basis_unit"] = (form.get("basis_unit") or "m2").strip()
    payload["per_basis_unit"] = payload["basis_unit"]
    payload["material_unit"] = (form.get("material_unit") or "").strip()
    payload["notes"] = form.get("notes") or None

    if not payload["material_name"]:
        errors.append("material_name")
    if payload["work_kind"] not in VALID_WORK_KINDS:
        errors.append("work_kind")
    if payload["basis_type"] not in VALID_BASIS_TYPES:
        errors.append("basis_type")
    if not payload["material_unit"]:
        errors.append("material_unit")

    try:
        payload["consumption_qty"] = _to_decimal(form.get("consumption_qty") or form.get("quantity_per_basis"), field="consumption_qty")
        payload["quantity_per_basis"] = payload["consumption_qty"]
        if payload["consumption_qty"] is not None and payload["consumption_qty"] <= 0:
            errors.append("quantity_per_basis")
    except ValueError:
        errors.append("quantity_per_basis")

    try:
        payload["waste_factor_pct"] = _to_decimal(form.get("waste_factor_pct") or "0", field="waste_factor_pct")
        if payload["waste_factor_pct"] is not None and payload["waste_factor_pct"] < 0:
            errors.append("waste_factor_pct")
    except ValueError:
        errors.append("waste_factor_pct")

    if payload["material_catalog_item_id"] not in (None, ""):
        try:
            payload["material_catalog_item_id"] = int(str(payload["material_catalog_item_id"]))
        except ValueError:
            errors.append("material_catalog_item_id")
    payload["applies_to_work_type"] = payload["work_kind"]
    payload["surface_type"] = {
        "wall_area": "wall",
        "ceiling_area": "ceiling",
        "floor_area": "floor",
    }.get(payload["basis_type"], "custom")
    payload["consumption_value"] = payload.get("consumption_qty") or Decimal("0")
    payload["consumption_unit"] = "per_1_m2"
    payload["waste_percent"] = payload.get("waste_factor_pct") or Decimal("0")
    payload["coats_multiplier_mode"] = "none"
    payload["layers_multiplier_enabled"] = form.get("layers_multiplier_enabled") in ("on", "true", "1", True, 1)

    return payload, errors


def _render_rules_form(request: Request, lang: str, norm: MaterialConsumptionNorm | None, errors: list[str], form_data: dict | None = None, catalog_items: list[MaterialCatalogItem] | None = None, status_code: int = 200):
    context = template_context(request, lang)
    context.update({"norm": norm, "errors": errors, "form_data": form_data or {}, "catalog_items": catalog_items or []})
    return templates.TemplateResponse(request, "materials/norms_form.html", context, status_code=status_code)


def _parse_catalog_form(form) -> tuple[dict, list[str]]:
    payload = {
        "material_code": (form.get("material_code") or "").strip().lower(),
        "name": (form.get("name") or "").strip(),
        "unit": (form.get("unit") or "").strip().lower(),
        "package_size": form.get("package_size"),
        "package_unit": (form.get("package_unit") or "").strip().lower(),
        "price_ex_vat": form.get("price_ex_vat"),
        "vat_rate_pct": form.get("vat_rate_pct") or "25",
        "supplier_name": (form.get("supplier_name") or "").strip() or None,
        "is_active": form.get("is_active") in ("on", "true", "1", True, 1),
        "is_default_for_material": form.get("is_default_for_material") in ("on", "true", "1", True, 1),
    }
    errors: list[str] = []
    for field in ("material_code", "name"):
        if not payload[field]:
            errors.append(field)
    if payload["unit"] not in VALID_UNITS:
        errors.append("unit")
    if payload["package_unit"] not in VALID_UNITS:
        errors.append("package_unit")
    try:
        payload["package_size"] = _to_decimal(payload["package_size"], field="package_size")
        if payload["package_size"] <= 0:
            errors.append("package_size")
    except ValueError:
        errors.append("package_size")
    try:
        payload["price_ex_vat"] = _to_decimal(payload["price_ex_vat"], field="price_ex_vat")
        if payload["price_ex_vat"] < 0:
            errors.append("price_ex_vat")
    except ValueError:
        errors.append("price_ex_vat")
    try:
        payload["vat_rate_pct"] = _to_decimal(payload["vat_rate_pct"], field="vat_rate_pct")
        if payload["vat_rate_pct"] < 0 or payload["vat_rate_pct"] > 100:
            errors.append("vat_rate_pct")
    except ValueError:
        errors.append("vat_rate_pct")
    return payload, errors


@router.get("/rules")
@router.get("/norms")
async def list_rules(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang), active: bool | None = None, material: str | None = None, work_type_code: str | None = None, basis_type: str | None = None):
    query = db.query(MaterialConsumptionNorm)
    if active is not None:
        query = query.filter(MaterialConsumptionNorm.active.is_(active))
    if material:
        query = query.filter(MaterialConsumptionNorm.material_name.ilike(f"%{material.strip()}%"))
    if work_type_code:
        query = query.filter(MaterialConsumptionNorm.work_type_code == work_type_code.strip())
    if basis_type:
        query = query.filter(MaterialConsumptionNorm.basis_type == basis_type.strip())
    norms = query.order_by(MaterialConsumptionNorm.id.desc()).all()
    context = template_context(request, lang)
    context["norms"] = norms
    return templates.TemplateResponse(request, "materials/norms_list.html", context)


@router.get("/rules/new")
@router.get("/norms/create")
async def rule_create_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    return _render_rules_form(request, lang, None, [], {}, db.query(MaterialCatalogItem).filter(MaterialCatalogItem.is_active.is_(True)).all())


@router.post("/rules/new")
@router.post("/norms/create")
async def rule_create(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    form = await request.form()
    payload, errors = _parse_rule_form(form)
    if payload.get("material_catalog_item_id") and not db.get(MaterialCatalogItem, payload["material_catalog_item_id"]):
        errors.append("material_catalog_item_id")
    if errors:
        return _render_rules_form(request, lang, None, errors, dict(form), db.query(MaterialCatalogItem).filter(MaterialCatalogItem.is_active.is_(True)).all(), status_code=422)
    db.add(MaterialConsumptionNorm(**payload))
    db.commit()
    return RedirectResponse(url="/materials/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/rules/{norm_id}/edit")
@router.get("/norms/{norm_id}/edit")
async def rule_edit_form(norm_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    norm = db.get(MaterialConsumptionNorm, norm_id)
    if not norm:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _render_rules_form(request, lang, norm, [], {}, db.query(MaterialCatalogItem).filter(MaterialCatalogItem.is_active.is_(True)).all())


@router.post("/rules/{norm_id}/edit")
@router.post("/norms/{norm_id}/edit")
async def rule_edit(norm_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    norm = db.get(MaterialConsumptionNorm, norm_id)
    if not norm:
        raise HTTPException(status_code=404, detail="Rule not found")
    form = await request.form()
    payload, errors = _parse_rule_form(form)
    if payload.get("material_catalog_item_id") and not db.get(MaterialCatalogItem, payload["material_catalog_item_id"]):
        errors.append("material_catalog_item_id")
    if errors:
        return _render_rules_form(request, lang, norm, errors, dict(form), db.query(MaterialCatalogItem).filter(MaterialCatalogItem.is_active.is_(True)).all(), status_code=422)
    for key, value in payload.items():
        setattr(norm, key, value)
    db.add(norm)
    db.commit()
    return RedirectResponse(url="/materials/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/rules/{norm_id}/delete")
@router.post("/norms/{norm_id}/delete")
async def rule_delete(norm_id: int, db: Session = Depends(get_db)):
    norm = db.get(MaterialConsumptionNorm, norm_id)
    if not norm:
        raise HTTPException(status_code=404, detail="Rule not found")
    norm.active = False
    norm.is_active = False
    db.add(norm)
    db.commit()
    return RedirectResponse(url="/materials/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/")
async def list_materials(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    materials = db.query(Material).all()
    context = template_context(request, lang)
    context["materials"] = materials
    return templates.TemplateResponse(request, "materials/list.html", context)


@router.get("/create")
async def new_material_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    context["material"] = None
    return templates.TemplateResponse(request, "materials/form.html", context)


@router.post("/create")
async def create_material(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    form = await request.form()
    material = Material(
        code=form.get("code"),
        name_ru=form.get("name_ru"),
        name_sv=form.get("name_sv"),
        category=form.get("category"),
        unit=form.get("unit"),
        default_price_per_unit=Decimal(form.get("default_price_per_unit") or "0"),
        moms_percent=Decimal(form.get("moms_percent") or "0"),
        is_active=bool(form.get("is_active")),
        comment=form.get("comment"),
    )
    db.add(material)
    db.commit()
    return RedirectResponse(url="/materials/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{material_id}/edit")
async def edit_material_form(material_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    context = template_context(request, lang)
    context["material"] = material
    return templates.TemplateResponse(request, "materials/form.html", context)


@router.post("/{material_id}/edit")
async def update_material(material_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    form = await request.form()
    material.code = form.get("code")
    material.name_ru = form.get("name_ru")
    material.name_sv = form.get("name_sv")
    material.category = form.get("category")
    material.unit = form.get("unit")
    material.default_price_per_unit = Decimal(form.get("default_price_per_unit") or "0")
    material.moms_percent = Decimal(form.get("moms_percent") or "0")
    material.is_active = bool(form.get("is_active"))
    material.comment = form.get("comment")

    db.add(material)
    db.commit()

    return RedirectResponse(url="/materials/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{material_id}/delete")
async def delete_material(material_id: int, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    db.delete(material)
    db.commit()
    return RedirectResponse(url="/materials/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/catalog")
async def catalog_list(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    items = db.query(MaterialCatalogItem).order_by(MaterialCatalogItem.material_code.asc(), MaterialCatalogItem.id.asc()).all()
    context = template_context(request, lang)
    context.update({"items": items})
    return templates.TemplateResponse(request, "materials/catalog_list.html", context)


@router.get("/catalog/new")
async def catalog_new_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    context.update({"item": None, "errors": []})
    return templates.TemplateResponse(request, "materials/catalog_form.html", context)


@router.post("/catalog/new")
async def catalog_new(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    form = await request.form()
    payload, errors = _parse_catalog_form(form)
    if errors:
        add_flash_message(request, f"Validation error: {', '.join(sorted(set(errors)))}", "error")
        context = template_context(request, lang)
        context.update({"item": None, "errors": errors, "form_data": dict(form)})
        return templates.TemplateResponse(request, "materials/catalog_form.html", context, status_code=422)
    db.add(MaterialCatalogItem(**payload))
    db.commit()
    add_flash_message(request, "Catalog item created", "success")
    return RedirectResponse(url="/materials/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/catalog/{item_id}/edit")
async def catalog_edit_form(item_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    item = db.get(MaterialCatalogItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    context = template_context(request, lang)
    context.update({"item": item, "errors": []})
    return templates.TemplateResponse(request, "materials/catalog_form.html", context)


@router.post("/catalog/{item_id}/edit")
async def catalog_edit(item_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    item = db.get(MaterialCatalogItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    form = await request.form()
    payload, errors = _parse_catalog_form(form)
    if errors:
        add_flash_message(request, f"Validation error: {', '.join(sorted(set(errors)))}", "error")
        context = template_context(request, lang)
        context.update({"item": item, "errors": errors, "form_data": dict(form)})
        return templates.TemplateResponse(request, "materials/catalog_form.html", context, status_code=422)
    for key, value in payload.items():
        setattr(item, key, value)
    db.add(item)
    db.commit()
    add_flash_message(request, "Catalog item updated", "success")
    return RedirectResponse(url="/materials/catalog", status_code=status.HTTP_303_SEE_OTHER)
    try:
        payload["per_basis_qty"] = _to_decimal(form.get("per_basis_qty") or "1", field="per_basis_qty")
        if payload["per_basis_qty"] is not None and payload["per_basis_qty"] <= 0:
            errors.append("per_basis_qty")
    except ValueError:
        errors.append("per_basis_qty")
