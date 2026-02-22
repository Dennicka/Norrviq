from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.material import Material

router = APIRouter(prefix="/materials", tags=["materials"])


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
