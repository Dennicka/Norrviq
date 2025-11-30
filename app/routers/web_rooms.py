from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.project import Project
from app.models.room import Room
from app.services.rooms import recalc_room_dimensions

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
    return templates.TemplateResponse("rooms/list.html", context)


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
    return templates.TemplateResponse("rooms/form.html", context)


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
    )
    recalc_room_dimensions(room)
    db.add(room)
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
    return templates.TemplateResponse("rooms/form.html", context)


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
    recalc_room_dimensions(room)

    db.add(room)
    db.commit()

    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{room_id}/delete")
async def delete_room(project_id: int, room_id: int, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if not room or room.project_id != project_id:
        raise HTTPException(status_code=404, detail="Room not found")

    db.delete(room)
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/rooms/", status_code=status.HTTP_303_SEE_OTHER)
