from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.material_norm import MaterialConsumptionNorm
from app.models.material import Material

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("/norms")
async def list_norms(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    norms = db.query(MaterialConsumptionNorm).order_by(MaterialConsumptionNorm.id.desc()).all()
    context = template_context(request, lang)
    context["norms"] = norms
    return templates.TemplateResponse(request, "materials/norms_list.html", context)


@router.get("/norms/create")
async def norm_create_form(request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    context = template_context(request, lang)
    context["norm"] = None
    return templates.TemplateResponse(request, "materials/norms_form.html", context)


@router.post("/norms/create")
async def norm_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    db.add(MaterialConsumptionNorm(
        active=form.get("active") in ("on", "true", "1", True, 1),
        material_name=form.get("material_name") or "",
        material_category=form.get("material_category") or "other",
        applies_to_work_type=form.get("applies_to_work_type") or "",
        surface_type=form.get("surface_type") or "custom",
        consumption_value=Decimal(form.get("consumption_value") or "0"),
        consumption_unit=form.get("consumption_unit") or "per_1_m2",
        material_unit=form.get("material_unit") or "pcs",
        package_size=Decimal(form.get("package_size")) if form.get("package_size") else None,
        package_unit=form.get("package_unit") or None,
        waste_percent=Decimal(form.get("waste_percent") or "10"),
        coats_multiplier_mode=form.get("coats_multiplier_mode") or "none",
        brand_product=form.get("brand_product") or None,
        default_unit_price_sek=Decimal(form.get("default_unit_price_sek")) if form.get("default_unit_price_sek") else None,
        notes=form.get("notes") or None,
    ))
    db.commit()
    return RedirectResponse(url="/materials/norms", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/norms/{norm_id}/edit")
async def norm_edit_form(norm_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)):
    norm = db.get(MaterialConsumptionNorm, norm_id)
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    context = template_context(request, lang)
    context["norm"] = norm
    return templates.TemplateResponse(request, "materials/norms_form.html", context)


@router.post("/norms/{norm_id}/edit")
async def norm_edit(norm_id: int, request: Request, db: Session = Depends(get_db)):
    norm = db.get(MaterialConsumptionNorm, norm_id)
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    form = await request.form()
    norm.active = form.get("active") in ("on", "true", "1", True, 1)
    norm.material_name = form.get("material_name") or norm.material_name
    norm.material_category = form.get("material_category") or "other"
    norm.applies_to_work_type = form.get("applies_to_work_type") or ""
    norm.surface_type = form.get("surface_type") or "custom"
    norm.consumption_value = Decimal(form.get("consumption_value") or "0")
    norm.consumption_unit = form.get("consumption_unit") or "per_1_m2"
    norm.material_unit = form.get("material_unit") or "pcs"
    norm.package_size = Decimal(form.get("package_size")) if form.get("package_size") else None
    norm.package_unit = form.get("package_unit") or None
    norm.waste_percent = Decimal(form.get("waste_percent") or "10")
    norm.coats_multiplier_mode = form.get("coats_multiplier_mode") or "none"
    norm.brand_product = form.get("brand_product") or None
    norm.default_unit_price_sek = Decimal(form.get("default_unit_price_sek")) if form.get("default_unit_price_sek") else None
    norm.notes = form.get("notes") or None
    db.add(norm)
    db.commit()
    return RedirectResponse(url="/materials/norms", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/norms/{norm_id}/delete")
async def norm_delete(norm_id: int, db: Session = Depends(get_db)):
    norm = db.get(MaterialConsumptionNorm, norm_id)
    if not norm:
        raise HTTPException(status_code=404, detail="Norm not found")
    db.delete(norm)
    db.commit()
    return RedirectResponse(url="/materials/norms", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/")
async def list_materials(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    materials = db.query(Material).all()
    context = template_context(request, lang)
    context["materials"] = materials
    return templates.TemplateResponse(request, "materials/list.html", context)


@router.get("/create")
async def new_material_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context["material"] = None
    return templates.TemplateResponse(request, "materials/form.html", context)


@router.post("/create")
async def create_material(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
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
async def edit_material_form(
    material_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    context = template_context(request, lang)
    context["material"] = material
    return templates.TemplateResponse(request, "materials/form.html", context)


@router.post("/{material_id}/edit")
async def update_material(
    material_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
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
async def delete_material(
    material_id: int,
    db: Session = Depends(get_db),
):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    db.delete(material)
    db.commit()
    return RedirectResponse(url="/materials/", status_code=status.HTTP_303_SEE_OTHER)
