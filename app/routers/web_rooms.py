from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import add_flash_message, get_current_lang, get_db, template_context, templates
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.services.rooms import recalc_room_dimensions
from app.services.quality import evaluate_project_quality
from app.i18n import make_t

router = APIRouter(prefix="/projects/{project_id}/rooms", tags=["rooms"])


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except Exception:
        return None


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
    context.update({"project": project, "rooms": rooms})
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
        floor_area_m2=_parse_decimal(form.get("floor_area_m2")),
        wall_perimeter_m=_parse_decimal(form.get("wall_perimeter_m")),
        wall_height_m=_parse_decimal(form.get("wall_height_m")),
        wall_area_m2=_parse_decimal(form.get("wall_area_m2")),
        ceiling_area_m2=_parse_decimal(form.get("ceiling_area_m2")),
        baseboard_length_m=_parse_decimal(form.get("baseboard_length_m")),
    )
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
    room.floor_area_m2 = _parse_decimal(form.get("floor_area_m2"))
    room.wall_perimeter_m = _parse_decimal(form.get("wall_perimeter_m"))
    room.wall_height_m = _parse_decimal(form.get("wall_height_m"))
    manual_wall_area = _parse_decimal(form.get("wall_area_m2"))
    manual_ceiling_area = _parse_decimal(form.get("ceiling_area_m2"))
    manual_baseboard = _parse_decimal(form.get("baseboard_length_m"))
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
