import json
import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.security import ADMIN_ROLE, OPERATOR_ROLE, get_current_user_email, require_role
from app.services.pricing import (
    PricingValidationError,
    get_or_create_project_buffer_settings,
    get_or_create_project_execution_profile,
    get_or_create_project_pricing,
    update_project_pricing,
)

router = APIRouter(prefix="/api/projects", tags=["api_projects_autosave"])
logger = logging.getLogger("uvicorn.error")


def _resp_ok(request: Request, updated_at) -> JSONResponse:
    return JSONResponse({"ok": True, "updated_at": updated_at.isoformat() if updated_at else None, "request_id": getattr(request.state, "request_id", None)})


def _resp_validation(request: Request, fields: dict[str, str], code: int = 422) -> JSONResponse:
    return JSONResponse(
        {"error": "validation", "fields": fields, "request_id": getattr(request.state, "request_id", None)},
        status_code=code,
    )


def _audit(db: Session, *, request: Request, entity_type: str, entity_id: int) -> None:
    db.add(
        AuditEvent(
            event_type="draft_autosave",
            user_id=get_current_user_email(request),
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps({"status": "ok", "request_id": getattr(request.state, "request_id", None)}),
        )
    )


@router.patch("/{project_id}/rooms/{room_id}", dependencies=[Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))])
async def patch_room(project_id: int, room_id: int, request: Request, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room or room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    payload = await request.json()
    allowed = {"name", "description", "length_m", "width_m", "floor_area_m2", "wall_perimeter_m", "wall_height_m", "openings_area_m2", "wall_area_m2", "ceiling_area_m2", "baseboard_length_m"}
    fields: dict[str, str] = {}

    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in {"name"} and not str(value or "").strip():
            fields[key] = "Required"
            continue
        if key.endswith("_m2") or key.endswith("_m"):
            if value in (None, ""):
                setattr(room, key, None)
                continue
            try:
                dec = Decimal(str(value))
            except (InvalidOperation, ValueError):
                fields[key] = "Must be numeric"
                continue
            if dec < 0:
                fields[key] = "Must be >= 0"
                continue
            setattr(room, key, dec)
        else:
            setattr(room, key, value)

    if fields:
        logger.warning("autosave_validation_failed entity=room room_id=%s request_id=%s", room_id, getattr(request.state, "request_id", None))
        return _resp_validation(request, fields)

    db.add(room)
    _audit(db, request=request, entity_type="room", entity_id=room.id)
    db.commit()
    db.refresh(room)
    return _resp_ok(request, room.updated_at)


@router.patch("/{project_id}/work-items/{item_id}", dependencies=[Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))])
async def patch_work_item(project_id: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(ProjectWorkItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=404, detail="Work item not found")
    payload = await request.json()
    fields: dict[str, str] = {}

    if "quantity" in payload:
        try:
            quantity = Decimal(str(payload.get("quantity")))
            if quantity <= 0:
                raise ValueError()
            item.quantity = quantity
        except Exception:
            fields["quantity"] = "Must be > 0"

    if "difficulty_factor" in payload:
        try:
            difficulty = Decimal(str(payload.get("difficulty_factor")))
            if difficulty <= 0:
                raise ValueError()
            item.difficulty_factor = difficulty
        except Exception:
            fields["difficulty_factor"] = "Must be > 0"

    if "comment" in payload:
        item.comment = payload.get("comment")

    if fields:
        logger.warning("autosave_validation_failed entity=work_item item_id=%s request_id=%s", item_id, getattr(request.state, "request_id", None))
        return _resp_validation(request, fields)

    db.add(item)
    _audit(db, request=request, entity_type="project_work_item", entity_id=item.id)
    db.commit()
    return _resp_ok(request, None)


@router.patch("/{project_id}/pricing", dependencies=[Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))])
async def patch_pricing(project_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    payload = await request.json()
    pricing = get_or_create_project_pricing(db, project_id)

    data = {k: v for k, v in payload.items() if k in {"mode", "hourly_rate_override", "fixed_total_price", "rate_per_m2", "rate_per_room", "rate_per_piece", "target_margin_pct", "include_materials", "include_travel_setup_buffers", "currency"}}
    if not data:
        return _resp_ok(request, pricing.updated_at)
    _audit(db, request=request, entity_type="project_pricing", entity_id=pricing.id)
    try:
        payload_for_update = {
            "mode": pricing.mode,
            "hourly_rate_override": pricing.hourly_rate_override,
            "fixed_total_price": pricing.fixed_total_price,
            "rate_per_m2": pricing.rate_per_m2,
            "rate_per_room": pricing.rate_per_room,
            "rate_per_piece": pricing.rate_per_piece,
            "target_margin_pct": pricing.target_margin_pct,
            "include_materials": pricing.include_materials,
            "include_travel_setup_buffers": pricing.include_travel_setup_buffers,
            "currency": pricing.currency,
        }
        payload_for_update.update(data)
        pricing = update_project_pricing(db, pricing=pricing, payload=payload_for_update, user_id=get_current_user_email(request))
    except PricingValidationError as exc:
        logger.warning("autosave_validation_failed entity=pricing project_id=%s request_id=%s", project_id, getattr(request.state, "request_id", None))
        return _resp_validation(request, exc.errors)

    db.refresh(pricing)
    return _resp_ok(request, pricing.updated_at)


@router.patch("/{project_id}/settings", dependencies=[Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE))])
async def patch_project_settings(project_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    payload = await request.json()
    buffer_settings = get_or_create_project_buffer_settings(db, project_id)
    execution_profile = get_or_create_project_execution_profile(db, project_id)

    if "include_setup_cleanup_travel" in payload:
        buffer_settings.include_setup_cleanup_travel = bool(payload.get("include_setup_cleanup_travel"))
    if "include_risk" in payload:
        buffer_settings.include_risk = bool(payload.get("include_risk"))
    if "speed_profile_id" in payload:
        raw = payload.get("speed_profile_id")
        execution_profile.speed_profile_id = int(raw) if raw not in (None, "") else None

    db.add(buffer_settings)
    db.add(execution_profile)
    _audit(db, request=request, entity_type="project", entity_id=project_id)
    db.commit()
    db.refresh(buffer_settings)
    return _resp_ok(request, buffer_settings.updated_at)
