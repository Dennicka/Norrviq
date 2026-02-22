from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectWorkItem
from app.models.project_buffer_settings import ProjectBufferSettings
from app.models.project_execution_profile import ProjectExecutionProfile
from app.models.project_pricing import ProjectPricing
from app.models.room import Room
from app.models.settings import get_or_create_settings
from app.models.speed_profile import SpeedProfile
from app.models.worktype import WorkType
from app.services.bootstrap import ensure_default_speed_profiles, ensure_default_worktypes
from app.services.estimates import calculate_work_item


@dataclass(frozen=True)
class LargeProjectSpec:
    rooms_count: int = 50
    work_items_count: int = 300


def create_large_project(db: Session, *, spec: LargeProjectSpec | None = None, name: str = "Large project") -> Project:
    """Create a deterministic large project for load/perf testing."""
    effective_spec = spec or LargeProjectSpec()

    ensure_default_worktypes(db)
    ensure_default_speed_profiles(db)
    settings = get_or_create_settings(db)

    hourly_rate = Decimal(str(settings.hourly_rate_company))

    project = Project(name=name)
    db.add(project)
    db.flush()

    rooms: list[Room] = []
    for idx in range(effective_spec.rooms_count):
        floor_area = Decimal("12.00") + Decimal(idx % 7) * Decimal("2.25")
        perimeter = Decimal("14.00") + Decimal(idx % 5) * Decimal("1.75")
        height = Decimal("2.70") + Decimal(idx % 4) * Decimal("0.10")
        room = Room(
            project_id=project.id,
            name=f"Room {idx + 1:02d}",
            floor_area_m2=floor_area,
            wall_perimeter_m=perimeter,
            wall_height_m=height,
            wall_area_m2=(perimeter * height).quantize(Decimal("0.01")),
            ceiling_area_m2=floor_area,
            baseboard_length_m=perimeter,
        )
        rooms.append(room)
    db.add_all(rooms)
    db.flush()

    worktypes = (
        db.query(WorkType)
        .filter(WorkType.is_active.is_(True))
        .order_by(WorkType.code.asc())
        .all()
    )
    if not worktypes:
        raise RuntimeError("No active work types available for large project generation")

    items: list[ProjectWorkItem] = []
    for idx in range(effective_spec.work_items_count):
        room = rooms[idx % len(rooms)]
        worktype = worktypes[idx % len(worktypes)]
        quantity = Decimal("1.00") + Decimal(idx % 9) * Decimal("0.50")
        difficulty = Decimal("1.00") + Decimal(idx % 4) * Decimal("0.05")
        item = ProjectWorkItem(
            project_id=project.id,
            room_id=room.id,
            work_type_id=worktype.id,
            quantity=quantity,
            difficulty_factor=difficulty,
        )
        calculate_work_item(item, worktype, hourly_rate)
        items.append(item)
    db.add_all(items)

    medium_profile = db.query(SpeedProfile).filter(SpeedProfile.code == "MEDIUM").first()
    if medium_profile is None:
        raise RuntimeError("MEDIUM speed profile is required but missing")

    db.add(
        ProjectExecutionProfile(
            project_id=project.id,
            speed_profile_id=medium_profile.id,
            apply_scope="PROJECT",
        )
    )
    db.add(
        ProjectBufferSettings(
            project_id=project.id,
            include_setup_cleanup_travel=True,
            include_risk=True,
        )
    )
    db.add(
        ProjectPricing(
            project_id=project.id,
            mode="HOURLY",
            include_materials=True,
            include_travel_setup_buffers=True,
        )
    )

    db.commit()
    db.refresh(project)
    return project
