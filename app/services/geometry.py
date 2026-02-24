from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.room import Room


@dataclass
class GeometryResult:
    floor_area_m2: Decimal | None = None
    ceiling_area_m2: Decimal | None = None
    perimeter_m: Decimal | None = None
    wall_area_gross_m2: Decimal | None = None
    openings_area_m2: Decimal = Decimal("0")
    wall_area_net_m2: Decimal | None = None
    baseboard_lm: Decimal | None = None
    cornice_lm: Decimal | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class GeometrySummary:
    total_floor_area_m2: Decimal = Decimal("0")
    total_ceiling_area_m2: Decimal = Decimal("0")
    total_wall_area_net_m2: Decimal = Decimal("0")
    total_wall_area_gross_m2: Decimal = Decimal("0")
    total_perimeter_m: Decimal = Decimal("0")
    total_openings_area_m2: Decimal = Decimal("0")
    rooms_count: int = 0
    warnings: list[str] = field(default_factory=list)


class GeometryValidationError(ValueError):
    pass


def _to_decimal(value, field_name: str, *, allow_none: bool = True) -> Decimal | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise GeometryValidationError(f"{field_name} is required")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise GeometryValidationError(f"{field_name} must be numeric") from exc
    if decimal_value < 0:
        raise GeometryValidationError(f"{field_name} can not be negative")
    return decimal_value


def _q(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.01"))


def compute_room_geometry(
    *,
    length_m=None,
    width_m=None,
    floor_area_m2=None,
    perimeter_m=None,
    ceiling_height_m=None,
    openings_area_m2=None,
) -> GeometryResult:
    length = _to_decimal(length_m, "length_m")
    width = _to_decimal(width_m, "width_m")
    floor_area = _to_decimal(floor_area_m2, "floor_area_m2")
    perimeter = _to_decimal(perimeter_m, "perimeter_m")
    ceiling_height = _to_decimal(ceiling_height_m, "ceiling_height_m")
    openings_area = _to_decimal(openings_area_m2, "openings_area_m2") or Decimal("0")

    result = GeometryResult(openings_area_m2=openings_area)

    if length is not None and width is not None:
        result.floor_area_m2 = length * width
        result.perimeter_m = Decimal("2") * (length + width)
    else:
        result.floor_area_m2 = floor_area
        result.perimeter_m = perimeter

    if result.floor_area_m2 is None:
        result.warnings.append("Не хватает площади пола: заполните floor_area_m2 или length_m/width_m")
    result.ceiling_area_m2 = result.floor_area_m2

    if ceiling_height is None:
        result.warnings.append("Не хватает высоты потолка: wall_area не может быть рассчитана")
    elif ceiling_height == 0:
        result.warnings.append("Высота потолка равна 0: wall_area не может быть рассчитана")

    if result.perimeter_m is None:
        result.warnings.append("Не хватает периметра: wall_area не может быть рассчитана")

    if result.perimeter_m is not None:
        result.baseboard_lm = result.perimeter_m
        result.cornice_lm = result.perimeter_m

    if result.perimeter_m is not None and ceiling_height is not None and ceiling_height > 0:
        result.wall_area_gross_m2 = result.perimeter_m * ceiling_height
        wall_net = result.wall_area_gross_m2 - openings_area
        if wall_net < 0:
            wall_net = Decimal("0")
            result.warnings.append("Площадь проемов больше площади стен: wall_area_net ограничена до 0")
        result.wall_area_net_m2 = wall_net

    result.floor_area_m2 = _q(result.floor_area_m2)
    result.ceiling_area_m2 = _q(result.ceiling_area_m2)
    result.perimeter_m = _q(result.perimeter_m)
    result.wall_area_gross_m2 = _q(result.wall_area_gross_m2)
    result.wall_area_net_m2 = _q(result.wall_area_net_m2)
    result.baseboard_lm = _q(result.baseboard_lm)
    result.cornice_lm = _q(result.cornice_lm)
    result.openings_area_m2 = _q(result.openings_area_m2) or Decimal("0.00")
    return result


def compute_room_geometry_from_model(room: Room) -> GeometryResult:
    return compute_room_geometry(
        length_m=room.length_m,
        width_m=room.width_m,
        floor_area_m2=room.floor_area_m2,
        perimeter_m=room.wall_perimeter_m,
        ceiling_height_m=room.wall_height_m,
        openings_area_m2=room.openings_area_m2,
    )


def aggregate_project_geometry(db: Session, project_id: int) -> GeometrySummary:
    rooms = db.query(Room).filter(Room.project_id == project_id).all()
    summary = GeometrySummary(rooms_count=len(rooms))
    for room in rooms:
        try:
            geometry = compute_room_geometry_from_model(room)
        except GeometryValidationError as exc:
            summary.warnings.append(f"Комната '{room.name}': {exc}")
            continue

        summary.total_floor_area_m2 += geometry.floor_area_m2 or Decimal("0")
        summary.total_ceiling_area_m2 += geometry.ceiling_area_m2 or Decimal("0")
        summary.total_wall_area_net_m2 += geometry.wall_area_net_m2 or Decimal("0")
        summary.total_wall_area_gross_m2 += geometry.wall_area_gross_m2 or Decimal("0")
        summary.total_perimeter_m += geometry.perimeter_m or Decimal("0")
        summary.total_openings_area_m2 += geometry.openings_area_m2 or Decimal("0")

        for warning in geometry.warnings:
            summary.warnings.append(f"Комната '{room.name}': {warning}")

    summary.total_floor_area_m2 = _q(summary.total_floor_area_m2) or Decimal("0.00")
    summary.total_ceiling_area_m2 = _q(summary.total_ceiling_area_m2) or Decimal("0.00")
    summary.total_wall_area_net_m2 = _q(summary.total_wall_area_net_m2) or Decimal("0.00")
    summary.total_wall_area_gross_m2 = _q(summary.total_wall_area_gross_m2) or Decimal("0.00")
    summary.total_perimeter_m = _q(summary.total_perimeter_m) or Decimal("0.00")
    summary.total_openings_area_m2 = _q(summary.total_openings_area_m2) or Decimal("0.00")
    return summary


def build_project_scope_metrics(rooms: list[Room]) -> GeometrySummary:
    summary = GeometrySummary(rooms_count=len(rooms))
    for room in rooms:
        try:
            geometry = compute_room_geometry_from_model(room)
        except GeometryValidationError as exc:
            summary.warnings.append(f"Комната '{room.name}': {exc}")
            continue

        summary.total_floor_area_m2 += geometry.floor_area_m2 or Decimal("0")
        summary.total_ceiling_area_m2 += geometry.ceiling_area_m2 or Decimal("0")
        summary.total_wall_area_net_m2 += geometry.wall_area_net_m2 or Decimal("0")
        summary.total_wall_area_gross_m2 += geometry.wall_area_gross_m2 or Decimal("0")
        summary.total_perimeter_m += geometry.perimeter_m or Decimal("0")
        summary.total_openings_area_m2 += geometry.openings_area_m2 or Decimal("0")

    summary.total_floor_area_m2 = _q(summary.total_floor_area_m2) or Decimal("0.00")
    summary.total_ceiling_area_m2 = _q(summary.total_ceiling_area_m2) or Decimal("0.00")
    summary.total_wall_area_net_m2 = _q(summary.total_wall_area_net_m2) or Decimal("0.00")
    summary.total_wall_area_gross_m2 = _q(summary.total_wall_area_gross_m2) or Decimal("0.00")
    summary.total_perimeter_m = _q(summary.total_perimeter_m) or Decimal("0.00")
    summary.total_openings_area_m2 = _q(summary.total_openings_area_m2) or Decimal("0.00")
    return summary
