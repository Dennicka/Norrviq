from decimal import Decimal

from sqlalchemy import func
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.settings import get_or_create_settings
from app.models.worktype import WorkType
from app.services.geometry import compute_room_geometry_from_model


class ProjectTotals(BaseModel):
    work_sum_without_moms: Decimal
    moms_amount: Decimal
    rot_amount: Decimal
    client_pays_total: Decimal


class BulkEstimateResult(BaseModel):
    created_item_ids: list[int]
    skipped_rooms: list[str]


def calculate_project_total_hours(db: Session, project_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(ProjectWorkItem.calculated_hours), 0))
        .filter(ProjectWorkItem.project_id == project_id)
        .scalar()
    )
    return Decimal(str(total or 0)).quantize(Decimal("0.01"))


def _resolve_bulk_quantity_for_room(room: Room, work_type: WorkType) -> Decimal | None:
    geometry = compute_room_geometry_from_model(room)
    unit = (work_type.unit or "").lower()
    category = (work_type.category or "").lower()

    if unit == "room":
        return Decimal("1.00")
    if unit == "m":
        return geometry.baseboard_lm
    if unit != "m2":
        return None

    if any(marker in category for marker in ("wall", "стен", "vägg")):
        return geometry.wall_area_net_m2
    if any(marker in category for marker in ("ceiling", "потол", "tak")):
        return geometry.ceiling_area_m2
    if any(marker in category for marker in ("floor", "пол", "golv")):
        return geometry.floor_area_m2
    return geometry.floor_area_m2


def estimate_project_work_bulk(
    db: Session,
    *,
    project: Project,
    work_type: WorkType,
    difficulty_factor: Decimal,
    comment: str | None,
) -> BulkEstimateResult:
    created_item_ids: list[int] = []
    skipped_rooms: list[str] = []
    rooms = db.query(Room).filter(Room.project_id == project.id).all()

    for room in rooms:
        quantity = _resolve_bulk_quantity_for_room(room, work_type)
        if quantity is None or quantity <= 0:
            skipped_rooms.append(room.name)
            continue

        item = ProjectWorkItem(
            project_id=project.id,
            work_type_id=work_type.id,
            room_id=room.id,
            quantity=quantity.quantize(Decimal("0.01")),
            difficulty_factor=difficulty_factor,
            comment=comment,
        )
        db.add(item)
        db.flush()
        created_item_ids.append(item.id)

    return BulkEstimateResult(created_item_ids=created_item_ids, skipped_rooms=skipped_rooms)


def calculate_work_item(
    item: ProjectWorkItem,
    work_type: WorkType,
    hourly_rate_company: Decimal,
) -> None:
    """
    Заполняет item.calculated_hours и item.calculated_cost_without_moms по формуле:

        base_hours = quantity * hours_per_unit
        hours_with_difficulty = base_hours * difficulty_factor
        cost_without_moms = hours_with_difficulty * hourly_rate_company
    """

    quantity = Decimal(str(item.quantity))
    hours_per_unit = Decimal(str(work_type.hours_per_unit))
    difficulty_factor = Decimal(str(item.difficulty_factor))

    base_hours = (quantity * hours_per_unit).quantize(Decimal("0.01"))
    hours_with_difficulty = (base_hours * difficulty_factor).quantize(Decimal("0.01"))
    cost_without_moms = (hours_with_difficulty * hourly_rate_company).quantize(Decimal("0.01"))

    item.calculated_hours = hours_with_difficulty
    item.calculated_cost_without_moms = cost_without_moms


def recalculate_project_work_items(db: Session, project: Project) -> None:
    settings = get_or_create_settings(db)
    hourly_rate = Decimal(str(settings.hourly_rate_company))

    for item in project.work_items:
        work_type = item.work_type
        calculate_work_item(item, work_type, hourly_rate)

    db.commit()


def calculate_project_totals(db: Session, project: Project) -> ProjectTotals:
    settings = get_or_create_settings(db)
    moms_rate = Decimal(str(settings.moms_percent)) / Decimal("100")
    rot_rate = Decimal(str(settings.rot_percent)) / Decimal("100")

    work_sum_without_moms = sum(
        (item.calculated_cost_without_moms or Decimal("0")) for item in project.work_items
    )

    moms_amount = (work_sum_without_moms * moms_rate).quantize(Decimal("0.01"))

    rot_amount = Decimal("0")
    if project.use_rot and project.client and project.client.is_rot_eligible:
        rot_amount = (work_sum_without_moms * rot_rate).quantize(Decimal("0.01"))

    client_pays_total = (work_sum_without_moms + moms_amount - rot_amount).quantize(Decimal("0.01"))

    project.work_sum_without_moms = work_sum_without_moms
    project.moms_amount = moms_amount
    project.rot_amount = rot_amount
    project.client_pays_total = client_pays_total
    db.commit()

    return ProjectTotals(
        work_sum_without_moms=work_sum_without_moms,
        moms_amount=moms_amount,
        rot_amount=rot_amount,
        client_pays_total=client_pays_total,
    )
