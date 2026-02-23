import json
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.i18n import make_t
from app.models.audit_event import AuditEvent
from app.models.project import Project, ProjectWorkItem
from app.models.paint_system import PaintSystem
from app.models.room import Room
from app.security import require_role
from app.services.quality import evaluate_project_quality
from app.services.materials_bom import get_or_create_room_paint_settings
from app.services.rooms import recalc_room_dimensions

router = APIRouter(prefix="/projects/{project_id}/rooms", tags=["rooms"])
logger = logging.getLogger("uvicorn.error")


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except Exception:
        return None


def _parse_n(value: str | None) -> int:
    try:
        n = int(value or "0")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="n must be between 1 and 200") from exc
    if n < 1 or n > 200:
        raise HTTPException(status_code=400, detail="n must be between 1 and 200")
    return n


def _build_copy_name(existing_names: set[str], source_name: str | None) -> str:
    base_name = (source_name or "Room").strip() or "Room"
    candidate = f"{base_name} (copy)"
    if candidate not in existing_names:
        return candidate
    index = 2
    while True:
        candidate = f"{base_name} #{index}"
        if candidate not in existing_names:
            return candidate
        index += 1


def _template_room_name(template: str, i: int) -> str:
    return (template or "Room {i}").replace("{i}", str(i)).strip()


def _validate_positive_decimal(field_name: str, value: Decimal | None) -> None:
    if value is not None and value <= 0:
        raise HTTPException(status_code=400, detail=f"{field_name} must be greater than 0")


def _validate_non_negative_decimal(field_name: str, value: Decimal | None) -> None:
    if value is not None and value < 0:
        raise HTTPException(status_code=400, detail=f"{field_name} can not be negative")


def _audit(db: Session, *, event_type: str, user_id: str | None, project_id: int, details: dict) -> None:
    db.add(
        AuditEvent(
            event_type=event_type,
            user_id=user_id,
            entity_type="project",
            entity_id=project_id,
            details=json.dumps(details, ensure_ascii=False),
        )
    )


def _clone_room(project_id: int, source: Room, name: str) -> Room:
    room = Room(
        project_id=project_id,
        name=name,
        description=source.description,
        length_m=source.length_m,
        width_m=source.width_m,
        floor_area_m2=source.floor_area_m2,
        wall_perimeter_m=source.wall_perimeter_m,
        wall_height_m=source.wall_height_m,
        openings_area_m2=source.openings_area_m2,
        wall_area_m2=source.wall_area_m2,
        ceiling_area_m2=source.ceiling_area_m2,
        baseboard_length_m=source.baseboard_length_m,
    )
    recalc_room_dimensions(room)
    return room


@router.get("/")
async def list_rooms(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.rooms))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    rooms = sorted(project.rooms, key=lambda r: r.name.lower() if r.name else "")
    context = template_context(request, lang)
    systems = db.query(PaintSystem).filter(PaintSystem.is_active.is_(True)).order_by(PaintSystem.name.asc(), PaintSystem.version.desc()).all()
    context.update({"project": project, "rooms": rooms, "paint_systems": systems})
    return templates.TemplateResponse(request, "rooms/list.html", context)


@router.get("/create")
async def create_room_form(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    context = template_context(request, lang)
    context.update({"project": project, "room": None})
    return templates.TemplateResponse(request, "rooms/form.html", context)


@router.post("/create")
async def create_room(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    room = Room(
        project_id=project.id,
        name=form.get("name"),
        description=form.get("description"),
        length_m=_parse_decimal(form.get("length_m")),
        width_m=_parse_decimal(form.get("width_m")),
        floor_area_m2=_parse_decimal(form.get("floor_area_m2")),
        wall_perimeter_m=_parse_decimal(form.get("wall_perimeter_m")),
        wall_height_m=_parse_decimal(form.get("wall_height_m")),
        openings_area_m2=_parse_decimal(form.get("openings_area_m2")),
        wall_area_m2=_parse_decimal(form.get("wall_area_m2")),
        ceiling_area_m2=_parse_decimal(form.get("ceiling_area_m2")),
        baseboard_length_m=_parse_decimal(form.get("baseboard_length_m")),
    )
    for field in ("length_m", "width_m", "floor_area_m2", "wall_perimeter_m", "wall_height_m", "openings_area_m2"):
        _validate_non_negative_decimal(field, getattr(room, field))
    recalc_room_dimensions(room)
    db.add(room)
    db.flush()
    quality_report = evaluate_project_quality(db, project.id, lang=lang)
    room_issues = [issue for issue in quality_report.issues if issue.entity == "ROOM" and issue.entity_id == room.id]
    block_issues = [issue for issue in room_issues if issue.severity == "BLOCK"]
    for issue in room_issues:
        add_flash_message(request, issue.message, "error" if issue.severity == "BLOCK" else "warning")
    if block_issues:
        db.rollback()
        return RedirectResponse(url=f"/projects/{project.id}/rooms/create", status_code=status.HTTP_303_SEE_OTHER)

    db.commit()
    return RedirectResponse(url=f"/projects/{project.id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{room_id}/edit")
async def edit_room_form(
    project_id: int,
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    room = db.get(Room, room_id)
    if not room or room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    context = template_context(request, lang)
    context.update({"project": room.project, "room": room})
    return templates.TemplateResponse(request, "rooms/form.html", context)


@router.post("/{room_id}/edit")
async def update_room(
    project_id: int,
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    room = db.get(Room, room_id)
    if not room or room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    form = await request.form()
    room.name = form.get("name")
    room.description = form.get("description")
    room.length_m = _parse_decimal(form.get("length_m"))
    room.width_m = _parse_decimal(form.get("width_m"))
    room.floor_area_m2 = _parse_decimal(form.get("floor_area_m2"))
    room.wall_perimeter_m = _parse_decimal(form.get("wall_perimeter_m"))
    room.wall_height_m = _parse_decimal(form.get("wall_height_m"))
    room.openings_area_m2 = _parse_decimal(form.get("openings_area_m2"))
    manual_wall_area = _parse_decimal(form.get("wall_area_m2"))
    manual_ceiling_area = _parse_decimal(form.get("ceiling_area_m2"))
    manual_baseboard = _parse_decimal(form.get("baseboard_length_m"))
    for field in ("length_m", "width_m", "floor_area_m2", "wall_perimeter_m", "wall_height_m", "openings_area_m2"):
        _validate_non_negative_decimal(field, getattr(room, field))
    recalc_room_dimensions(room)
    if manual_wall_area is not None:
        room.wall_area_m2 = manual_wall_area
    if manual_ceiling_area is not None:
        room.ceiling_area_m2 = manual_ceiling_area
    if manual_baseboard is not None:
        room.baseboard_length_m = manual_baseboard

    db.add(room)
    db.flush()
    quality_report = evaluate_project_quality(db, project_id, lang=lang)
    room_issues = [issue for issue in quality_report.issues if issue.entity == "ROOM" and issue.entity_id == room.id]
    block_issues = [issue for issue in room_issues if issue.severity == "BLOCK"]
    for issue in room_issues:
        add_flash_message(request, issue.message, "error" if issue.severity == "BLOCK" else "warning")
    if block_issues:
        db.rollback()
        return RedirectResponse(url=f"/projects/{project_id}/rooms/{room_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{room_id}/delete")
async def delete_room(
    project_id: int,
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    translator = make_t(lang)
    room = db.get(Room, room_id)
    if not room or room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    usage_count = (
        db.query(ProjectWorkItem)
        .filter(ProjectWorkItem.room_id == room_id, ProjectWorkItem.project_id == project_id)
        .count()
    )
    if usage_count:
        add_flash_message(request, translator("rooms.delete.blocked"), "error")
        return RedirectResponse(
            url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER
        )

    db.delete(room)
    db.commit()
    add_flash_message(request, translator("rooms.delete.success"), "success")
    return RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{room_id}/duplicate")
async def duplicate_room(
    project_id: int,
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    source_room = db.get(Room, room_id)
    if not source_room or source_room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    existing_names = {name for (name,) in db.query(Room.name).filter(Room.project_id == project_id).all()}
    new_room = _clone_room(project_id, source_room, _build_copy_name(existing_names, source_room.name))
    db.add(new_room)
    db.flush()

    evaluate_project_quality(db, project_id, lang=lang)
    user_id = request.session.get("user_email") if hasattr(request, "session") else None
    _audit(db, event_type="room_duplicated", user_id=user_id, project_id=project_id, details={"source_room_id": room_id, "new_room_id": new_room.id})

    logger.info(
        "event=room_duplicated project_id=%s count=%s request_id=%s",
        project_id,
        1,
        getattr(request.state, "request_id", None),
    )
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{room_id}/duplicate_many")
async def duplicate_many_rooms(
    project_id: int,
    room_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    source_room = db.get(Room, room_id)
    if not source_room or source_room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    form = await request.form()
    n = _parse_n(form.get("n"))

    prefix = (form.get("name_prefix") or "").strip()
    existing_names = {name for (name,) in db.query(Room.name).filter(Room.project_id == project_id).all()}
    new_rooms: list[Room] = []
    for i in range(1, n + 1):
        if prefix:
            new_name = f"{prefix} {i}".strip()
            if new_name in existing_names:
                new_name = _build_copy_name(existing_names, new_name)
        else:
            new_name = _build_copy_name(existing_names, source_room.name)
        if len(new_name) > 255:
            raise HTTPException(status_code=400, detail="room name is too long")
        existing_names.add(new_name)
        new_rooms.append(_clone_room(project_id, source_room, new_name))

    db.bulk_save_objects(new_rooms)
    evaluate_project_quality(db, project_id, lang=lang)
    user_id = request.session.get("user_email") if hasattr(request, "session") else None
    _audit(
        db,
        event_type="rooms_bulk_created",
        user_id=user_id,
        project_id=project_id,
        details={"source_room_id": room_id, "count": n, "mode": "duplicate_many"},
    )
    logger.info(
        "event=rooms_bulk_created project_id=%s count=%s request_id=%s",
        project_id,
        n,
        getattr(request.state, "request_id", None),
    )
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk_create")
async def bulk_create_rooms(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form = await request.form()
    n = _parse_n(form.get("n"))

    name_template = (form.get("name_template") or "Room {i}").strip() or "Room {i}"
    floor_area_m2 = _parse_decimal(form.get("floor_area_m2"))
    wall_perimeter_m = _parse_decimal(form.get("wall_perimeter_m"))
    wall_height_m = _parse_decimal(form.get("wall_height_m"))
    ceiling_area_m2 = _parse_decimal(form.get("ceiling_area_m2"))
    _validate_positive_decimal("floor_area_m2", floor_area_m2)
    _validate_positive_decimal("wall_perimeter_m", wall_perimeter_m)
    _validate_positive_decimal("wall_height_m", wall_height_m)
    _validate_positive_decimal("ceiling_area_m2", ceiling_area_m2)

    existing_names = {name for (name,) in db.query(Room.name).filter(Room.project_id == project_id).all()}
    rooms_to_create: list[Room] = []
    for i in range(1, n + 1):
        generated_name = _template_room_name(name_template, i)
        if not generated_name:
            raise HTTPException(status_code=400, detail="generated room name can not be empty")
        if len(generated_name) > 255:
            raise HTTPException(status_code=400, detail="room name is too long")
        if generated_name in existing_names:
            generated_name = _build_copy_name(existing_names, generated_name)
        existing_names.add(generated_name)
        room = Room(
            project_id=project_id,
            name=generated_name,
            floor_area_m2=floor_area_m2,
            wall_perimeter_m=wall_perimeter_m,
            wall_height_m=wall_height_m,
            ceiling_area_m2=ceiling_area_m2,
        )
        recalc_room_dimensions(room)
        rooms_to_create.append(room)

    db.bulk_save_objects(rooms_to_create)
    evaluate_project_quality(db, project_id, lang=lang)
    user_id = request.session.get("user_email") if hasattr(request, "session") else None
    _audit(db, event_type="rooms_bulk_created", user_id=user_id, project_id=project_id, details={"count": n, "template": name_template})
    logger.info(
        "event=rooms_bulk_created project_id=%s count=%s request_id=%s",
        project_id,
        n,
        getattr(request.state, "request_id", None),
    )
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk_update")
async def bulk_update_rooms(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    form = await request.form()
    raw_room_ids = form.getlist("room_ids")
    if not raw_room_ids:
        raise HTTPException(status_code=400, detail="room_ids are required")

    try:
        room_ids = [int(value) for value in raw_room_ids]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="room_ids must be integers") from exc

    apply_if_empty = form.get("apply_if_empty") in ("on", "true", "1")
    height = _parse_decimal(form.get("wall_height_m"))
    description = form.get("description")
    wall_system_id = int(form.get("wall_paint_system_id")) if form.get("wall_paint_system_id") else None
    ceiling_system_id = int(form.get("ceiling_paint_system_id")) if form.get("ceiling_paint_system_id") else None
    if height is None and (description is None or description == "") and wall_system_id is None and ceiling_system_id is None:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    _validate_positive_decimal("wall_height_m", height)

    rooms = db.query(Room).filter(Room.project_id == project_id, Room.id.in_(room_ids)).all()
    if len(rooms) != len(set(room_ids)):
        raise HTTPException(status_code=404, detail="Some rooms were not found")

    changed = 0
    changed_fields: set[str] = set()
    for room in rooms:
        room_changed = False
        if height is not None and (not apply_if_empty or room.wall_height_m in (None, Decimal("0"))):
            room.wall_height_m = height
            changed_fields.add("wall_height_m")
            room_changed = True
        if description is not None and description != "" and (not apply_if_empty or not room.description):
            room.description = description
            changed_fields.add("description")
            room_changed = True
        if wall_system_id is not None:
            rps = get_or_create_room_paint_settings(db, room.id)
            rps.wall_paint_system_id = wall_system_id
            db.add(rps)
            changed_fields.add("wall_paint_system_id")
            room_changed = True
        if ceiling_system_id is not None:
            rps = get_or_create_room_paint_settings(db, room.id)
            rps.ceiling_paint_system_id = ceiling_system_id
            db.add(rps)
            changed_fields.add("ceiling_paint_system_id")
            room_changed = True
        if room_changed:
            recalc_room_dimensions(room)
            changed += 1
            db.add(room)

    evaluate_project_quality(db, project_id, lang=lang)
    user_id = request.session.get("user_email") if hasattr(request, "session") else None
    _audit(
        db,
        event_type="rooms_bulk_updated",
        user_id=user_id,
        project_id=project_id,
        details={"count": changed, "fields": sorted(changed_fields), "apply_if_empty": apply_if_empty},
    )
    logger.info(
        "event=rooms_bulk_updated project_id=%s count=%s request_id=%s",
        project_id,
        changed,
        getattr(request.state, "request_id", None),
    )
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)
