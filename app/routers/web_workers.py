from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.settings import get_or_create_settings
from app.models.worker import Worker
from app.models.speed_profile import SpeedProfile
from app.models.audit_event import AuditEvent
from app.security import require_role
from app.services.workers import get_worker_aggregates

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("/")
async def list_workers(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    workers = db.query(Worker).all()
    settings = get_or_create_settings(db)
    aggregates = get_worker_aggregates(db, workers, settings)

    context = template_context(request, lang)
    context.update({"workers": workers, "aggregates": aggregates})
    return templates.TemplateResponse(request, "workers/list.html", context)


@router.get("/new")
async def new_worker_form(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang)
):
    profiles = db.query(SpeedProfile).filter(SpeedProfile.is_active.is_(True)).order_by(SpeedProfile.code.asc()).all()
    context = template_context(request, lang)
    context.update({"worker": None, "speed_profiles": profiles})
    return templates.TemplateResponse(request, "workers/form.html", context)


@router.post("/new")
async def create_worker(
    request: Request, db: Session = Depends(get_db), lang: str = Depends(get_current_lang), _role: str = Depends(require_role("admin", "operator"))
):
    form = await request.form()
    hourly_rate = form.get("hourly_rate")
    default_tax_percent_for_net = form.get("default_tax_percent_for_net")
    worker = Worker(
        name=form.get("name"),
        role=form.get("role"),
        hourly_rate=Decimal(hourly_rate) if hourly_rate else None,
        default_tax_percent_for_net=Decimal(default_tax_percent_for_net)
        if default_tax_percent_for_net
        else None,
        is_active=bool(form.get("is_active")),
        default_speed_profile_id=int(form.get("default_speed_profile_id")) if form.get("default_speed_profile_id") else None,
    )
    db.add(worker)
    db.add(AuditEvent(event_type="employee_speed_profile_updated", user_id=request.session.get("user_email") if hasattr(request, "session") else None, entity_type="worker", entity_id=worker.id or 0, details="{}"))
    db.commit()
    return RedirectResponse(url="/workers/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{worker_id}/edit")
async def edit_worker_form(
    worker_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    worker = db.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    profiles = db.query(SpeedProfile).filter(SpeedProfile.is_active.is_(True)).order_by(SpeedProfile.code.asc()).all()
    context = template_context(request, lang)
    context.update({"worker": worker, "speed_profiles": profiles})
    return templates.TemplateResponse(request, "workers/form.html", context)


@router.post("/{worker_id}/edit")
async def update_worker(
    worker_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    worker = db.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    form = await request.form()
    hourly_rate = form.get("hourly_rate")
    default_tax_percent_for_net = form.get("default_tax_percent_for_net")
    worker.name = form.get("name")
    worker.role = form.get("role")
    worker.hourly_rate = Decimal(hourly_rate) if hourly_rate else None
    worker.default_tax_percent_for_net = (
        Decimal(default_tax_percent_for_net) if default_tax_percent_for_net else None
    )
    worker.is_active = bool(form.get("is_active"))
    worker.default_speed_profile_id = int(form.get("default_speed_profile_id")) if form.get("default_speed_profile_id") else None

    db.add(worker)
    db.add(AuditEvent(event_type="employee_speed_profile_updated", user_id=request.session.get("user_email") if hasattr(request, "session") else None, entity_type="worker", entity_id=worker.id, details="{}"))
    db.commit()

    return RedirectResponse(url="/workers/", status_code=status.HTTP_303_SEE_OTHER)
