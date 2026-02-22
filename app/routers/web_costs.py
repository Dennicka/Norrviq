from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.cost import CostCategory

router = APIRouter(prefix="/cost-categories", tags=["cost_categories"])


@router.get("/")
async def list_cost_categories(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    categories = db.query(CostCategory).all()
    context = template_context(request, lang)
    context["categories"] = categories
    return templates.TemplateResponse(request, "cost_categories/list.html", context)


@router.get("/new")
async def new_cost_category_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    context = template_context(request, lang)
    context["category"] = None
    context["code_readonly"] = False
    return templates.TemplateResponse(request, "cost_categories/form.html", context)


@router.post("/new")
async def create_cost_category(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    form = await request.form()
    category = CostCategory(
        code=form.get("code"), name_ru=form.get("name_ru"), name_sv=form.get("name_sv")
    )
    db.add(category)
    db.commit()
    return RedirectResponse(url="/cost-categories/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{category_id}/edit")
async def edit_cost_category_form(
    category_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    category = db.get(CostCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="CostCategory not found")
    context = template_context(request, lang)
    context["category"] = category
    context["code_readonly"] = True
    return templates.TemplateResponse(request, "cost_categories/form.html", context)


@router.post("/{category_id}/edit")
async def update_cost_category(
    category_id: int, request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    category = db.get(CostCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="CostCategory not found")

    form = await request.form()
    category.name_ru = form.get("name_ru")
    category.name_sv = form.get("name_sv")

    db.add(category)
    db.commit()

    return RedirectResponse(url="/cost-categories/", status_code=status.HTTP_303_SEE_OTHER)
