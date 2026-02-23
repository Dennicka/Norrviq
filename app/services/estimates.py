from decimal import Decimal
from enum import Enum

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


class WorkItemPricingMode(str, Enum):
    HOURLY = "hourly"
    AREA = "area"
    FIXED = "fixed"


class ProjectPricingTotals(BaseModel):
    total_labor_hours: Decimal
    total_price_sek: Decimal
    total_cost_sek: Decimal
    total_margin_sek: Decimal
    total_margin_pct: Decimal


def _norm_mode(value: str | None) -> WorkItemPricingMode:
    try:
        return WorkItemPricingMode((value or WorkItemPricingMode.HOURLY.value).lower())
    except ValueError:
        return WorkItemPricingMode.HOURLY


def resolve_billable_area_m2(item: ProjectWorkItem, work_type: WorkType) -> Decimal:
    room = item.room
    if room is None:
        return Decimal("0.00")

    category = (work_type.category or "").lower()
    if any(marker in category for marker in ("ceiling", "потол", "tak")):
        return Decimal(str(room.ceiling_area_m2 or 0)).quantize(Decimal("0.01"))
    if any(marker in category for marker in ("wall", "стен", "vägg")):
        return Decimal(str(room.wall_area_m2 or 0)).quantize(Decimal("0.01"))
    if any(marker in category for marker in ("floor", "пол", "golv", "protect", "защит", "skydd")):
        return Decimal(str(room.floor_area_m2 or 0)).quantize(Decimal("0.01"))
    return Decimal(str(room.floor_area_m2 or 0)).quantize(Decimal("0.01"))


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
    pricing_mode: str = WorkItemPricingMode.HOURLY.value,
    hourly_rate_sek: Decimal | None = None,
    area_rate_sek: Decimal | None = None,
    fixed_price_sek: Decimal | None = None,
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
            quantity=quantity.quantize(Decimal("0.01"),),
            difficulty_factor=difficulty_factor,
            pricing_mode=_norm_mode(pricing_mode).value,
            hourly_rate_sek=hourly_rate_sek,
            area_rate_sek=area_rate_sek,
            fixed_price_sek=fixed_price_sek,
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
    internal_labor_cost_rate_sek: Decimal = Decimal("0"),
) -> None:
    quantity = Decimal(str(item.quantity))
    hours_per_unit = Decimal(str(work_type.hours_per_unit))
    difficulty_factor = Decimal(str(item.difficulty_factor))

    base_hours = (quantity * hours_per_unit).quantize(Decimal("0.01"))
    labor_hours = (base_hours * difficulty_factor).quantize(Decimal("0.01"))

    item.calculated_hours = labor_hours

    mode = _norm_mode(getattr(item, "pricing_mode", None))
    price_sek = Decimal("0.00")

    if mode is WorkItemPricingMode.HOURLY:
        rate = Decimal(str(item.hourly_rate_sek if item.hourly_rate_sek is not None else hourly_rate_company))
        item.hourly_rate_sek = rate.quantize(Decimal("0.01"))
        price_sek = (labor_hours * rate).quantize(Decimal("0.01"))
    elif mode is WorkItemPricingMode.AREA:
        area_rate = Decimal(str(item.area_rate_sek or 0)).quantize(Decimal("0.01"))
        billable_area = resolve_billable_area_m2(item, work_type)
        item.billable_area_m2 = billable_area
        item.area_rate_sek = area_rate
        price_sek = (billable_area * area_rate).quantize(Decimal("0.01"))
    else:
        fixed_price = Decimal(str(item.fixed_price_sek or 0)).quantize(Decimal("0.01"))
        item.fixed_price_sek = fixed_price
        price_sek = fixed_price

    labor_cost_sek = (labor_hours * internal_labor_cost_rate_sek).quantize(Decimal("0.01"))
    materials_cost_sek = Decimal(str(item.materials_cost_sek or 0)).quantize(Decimal("0.01"))
    total_cost_sek = (labor_cost_sek + materials_cost_sek).quantize(Decimal("0.01"))
    margin_sek = (price_sek - total_cost_sek).quantize(Decimal("0.01"))
    margin_pct = Decimal("0.00")
    if price_sek > 0:
        margin_pct = ((margin_sek / price_sek) * Decimal("100")).quantize(Decimal("0.01"))

    item.pricing_mode = mode.value
    item.calculated_cost_without_moms = price_sek
    item.labor_cost_sek = labor_cost_sek
    item.total_cost_sek = total_cost_sek
    item.margin_sek = margin_sek
    item.margin_pct = margin_pct


def calculate_project_pricing_totals(project: Project) -> ProjectPricingTotals:
    total_labor_hours = sum((Decimal(str(item.calculated_hours or 0)) for item in project.work_items), Decimal("0"))
    total_price_sek = sum((Decimal(str(item.calculated_cost_without_moms or 0)) for item in project.work_items), Decimal("0"))
    total_cost_sek = sum((Decimal(str(item.total_cost_sek or 0)) for item in project.work_items), Decimal("0"))
    total_margin_sek = (total_price_sek - total_cost_sek).quantize(Decimal("0.01"))
    total_margin_pct = Decimal("0.00")
    if total_price_sek > 0:
        total_margin_pct = ((total_margin_sek / total_price_sek) * Decimal("100")).quantize(Decimal("0.01"))

    return ProjectPricingTotals(
        total_labor_hours=total_labor_hours.quantize(Decimal("0.01")),
        total_price_sek=total_price_sek.quantize(Decimal("0.01")),
        total_cost_sek=total_cost_sek.quantize(Decimal("0.01")),
        total_margin_sek=total_margin_sek,
        total_margin_pct=total_margin_pct,
    )


def recalculate_project_work_items(db: Session, project: Project) -> None:
    settings = get_or_create_settings(db)
    hourly_rate = Decimal(str(settings.hourly_rate_company))
    internal_labor_cost_rate = Decimal(str(settings.internal_labor_cost_rate_sek or 0))

    for item in project.work_items:
        work_type = item.work_type
        calculate_work_item(item, work_type, hourly_rate, internal_labor_cost_rate)

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
