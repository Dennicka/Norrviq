from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_takeoff_settings import DEFAULT_M2_BASIS, M2_BASIS_CHOICES, ProjectTakeoffSettings

AREA_QUANT = Decimal("0.01")


@dataclass
class RoomAreaBreakdown:
    room_id: int
    room_name: str
    floor_area_m2: Decimal
    ceiling_area_m2: Decimal
    wall_area_m2: Decimal
    warnings: list[str]


@dataclass
class AreasBreakdown:
    rooms: list[RoomAreaBreakdown]
    total_floor_m2: Decimal
    total_ceiling_m2: Decimal
    total_wall_m2: Decimal
    total_paintable_m2: Decimal

    def total_by_basis(self, basis: str) -> Decimal:
        if basis == "WALL_AREA":
            return self.total_wall_m2
        if basis == "CEILING_AREA":
            return self.total_ceiling_m2
        if basis == "PAINTABLE_TOTAL":
            return self.total_paintable_m2
        return self.total_floor_m2


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(AREA_QUANT)


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def get_or_create_project_takeoff_settings(db: Session, project_id: int) -> ProjectTakeoffSettings:
    settings = db.query(ProjectTakeoffSettings).filter(ProjectTakeoffSettings.project_id == project_id).first()
    if settings:
        return settings
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")
    settings = ProjectTakeoffSettings(project_id=project_id, m2_basis=DEFAULT_M2_BASIS)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def compute_project_areas(db: Session, project_id: int) -> AreasBreakdown:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")
    takeoff_settings = get_or_create_project_takeoff_settings(db, project_id)

    rooms: list[RoomAreaBreakdown] = []
    total_floor = Decimal("0")
    total_ceiling = Decimal("0")
    total_wall = Decimal("0")

    for room in project.rooms:
        floor_area = _to_decimal(room.floor_area_m2)
        if room.ceiling_area_m2 is not None:
            ceiling_area = _to_decimal(room.ceiling_area_m2)
        else:
            ceiling_area = floor_area
        warnings: list[str] = []

        room_wall_area = _to_decimal(room.wall_area_m2)
        if room.wall_area_m2 is not None and room_wall_area > 0:
            wall_area = room_wall_area
        else:
            if room.wall_perimeter_m is None or room.wall_height_m is None:
                wall_area = Decimal("0")
                warnings.append("MISSING_PERIMETER_OR_HEIGHT")
            else:
                wall_area = _to_decimal(room.wall_perimeter_m) * _to_decimal(room.wall_height_m)

            if takeoff_settings.include_openings_subtraction:
                wall_area -= _to_decimal(room.openings_area_m2)
                if wall_area < 0:
                    wall_area = Decimal("0")
                    warnings.append("OPENINGS_EXCEED_WALLS")

        floor_area = _quantize(floor_area)
        ceiling_area = _quantize(ceiling_area)
        wall_area = _quantize(wall_area)

        total_floor += floor_area
        total_ceiling += ceiling_area
        total_wall += wall_area
        rooms.append(
            RoomAreaBreakdown(
                room_id=room.id,
                room_name=room.name,
                floor_area_m2=floor_area,
                ceiling_area_m2=ceiling_area,
                wall_area_m2=wall_area,
                warnings=warnings,
            )
        )

    total_floor = _quantize(total_floor)
    total_ceiling = _quantize(total_ceiling)
    total_wall = _quantize(total_wall)
    return AreasBreakdown(
        rooms=rooms,
        total_floor_m2=total_floor,
        total_ceiling_m2=total_ceiling,
        total_wall_m2=total_wall,
        total_paintable_m2=_quantize(total_wall + total_ceiling),
    )


def validate_m2_basis(value: str | None) -> str:
    basis = (value or DEFAULT_M2_BASIS).upper()
    if basis not in M2_BASIS_CHOICES:
        raise ValueError("Invalid m2 basis")
    return basis
