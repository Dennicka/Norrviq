from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.scripts.seed_defaults import seed_defaults
from app.services.bootstrap import ensure_default_worktypes
from app.services.work_packages import ensure_default_packages
from app.services.work_packages_apply import apply_package
from tests.db_utils import upgrade_database


def _seed_project_with_rooms(db, *, rooms: int = 1) -> tuple[int, list[int]]:
    project = Project(name=f"Work package {uuid4().hex[:6]}")
    db.add(project)
    db.flush()

    room_ids: list[int] = []
    for index in range(rooms):
        room = Room(
            project_id=project.id,
            name=f"Room {index + 1}",
            floor_area_m2=Decimal("12"),
            wall_area_m2=Decimal("30"),
            ceiling_area_m2=Decimal("12"),
            wall_perimeter_m=Decimal("14"),
        )
        db.add(room)
        db.flush()
        room_ids.append(room.id)

    db.commit()
    return project.id, room_ids


def test_work_package_templates_have_valid_work_type_codes(tmp_path: Path):
    db_path = tmp_path / "work-packages.sqlite3"
    db_url = f"sqlite:///{db_path}"
    upgrade_database(db_url)

    engine = create_engine(db_url)
    LocalSession = sessionmaker(bind=engine)
    db = LocalSession()
    try:
        ensure_default_worktypes(db)
        ensure_default_packages(db)
    finally:
        db.close()

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT i.work_type_code
                FROM work_package_template_items i
                JOIN work_package_templates t ON t.id = i.template_id
                LEFT JOIN work_types wt ON wt.code = i.work_type_code
                WHERE t.is_active = 1 AND wt.code IS NULL
                """
            )
        ).all()
    assert rows == []


def test_apply_pkg_paint_walls_2_creates_two_coat_items():
    db = SessionLocal()
    try:
        seed_defaults(db)
        project_id, _ = _seed_project_with_rooms(db, rooms=1)

        summary = apply_package(
            db,
            project_id=project_id,
            package_code="PKG_PAINT_WALL_2",
            scope_mode="WHOLE_PROJECT",
            selected_room_ids=[],
        )

        assert summary.created_count == 2
        assert summary.missing_work_type_codes == ()

        items = (
            db.query(ProjectWorkItem)
            .join(WorkType, WorkType.id == ProjectWorkItem.work_type_id)
            .filter(ProjectWorkItem.project_id == project_id)
            .all()
        )
        codes = sorted(item.work_type.code for item in items)
        assert codes == ["WALL_PAINT_COAT_1", "WALL_PAINT_COAT_2"]
    finally:
        db.rollback()
        db.close()


def test_apply_pkg_selected_rooms_creates_items_per_room():
    db = SessionLocal()
    try:
        seed_defaults(db)
        project_id, room_ids = _seed_project_with_rooms(db, rooms=2)
        selected_room_id = room_ids[0]

        summary = apply_package(
            db,
            project_id=project_id,
            package_code="PKG_PAINT_WALL_2",
            scope_mode="SELECTED_ROOMS",
            selected_room_ids=[selected_room_id],
        )

        assert summary.created_count == 2

        created = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).all()
        assert len(created) == 2
        assert all(item.scope_mode == "SELECTED_ROOMS" for item in created)
        assert all(item.selected_room_ids_json == f"[{selected_room_id}]" for item in created)
    finally:
        db.rollback()
        db.close()
