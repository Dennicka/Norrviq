from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.work_scope_apply import apply_work_item_to_scope


def _seed_project(db):
    project = Project(name=f"Scope Apply {uuid4().hex[:8]}")
    wt = WorkType(
        code=f"WT-SCOPE-{uuid4().hex[:8]}",
        category="wall paint",
        unit="m2",
        name_ru="Покраска стен",
        name_sv="Väggmålning",
        hours_per_unit=Decimal("1.0"),
        base_difficulty_factor=Decimal("1.0"),
        is_active=True,
    )
    r1 = Room(project=project, name="R1", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2.5"))
    r2 = Room(project=project, name="R2", floor_area_m2=Decimal("12"), wall_perimeter_m=Decimal("8"), wall_height_m=Decimal("2.5"))
    r3 = Room(project=project, name="R3", floor_area_m2=Decimal("9"), wall_perimeter_m=None, wall_height_m=None)
    db.add_all([project, wt, r1, r2, r3])
    db.commit()
    db.refresh(project)
    db.refresh(wt)
    db.refresh(r1)
    db.refresh(r2)
    db.refresh(r3)
    return project, wt, r1, r2, r3


def test_single_room_creates_one_item():
    db = SessionLocal()
    try:
        project, wt, r1, _, _ = _seed_project(db)
        result = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "single_room", "room_id": r1.id}, db)
        assert result.created_count == 1
    finally:
        db.rollback()
        db.close()


def test_selected_rooms_creates_only_selected_items():
    db = SessionLocal()
    try:
        project, wt, r1, r2, _ = _seed_project(db)
        result = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "selected_rooms", "selected_room_ids": [r2.id]}, db)
        assert result.created_count == 1
        created = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project.id).all()
        assert {item.room_id for item in created} == {r2.id}
    finally:
        db.rollback()
        db.close()


def test_all_rooms_creates_for_valid_rooms():
    db = SessionLocal()
    try:
        project, wt, _, _, _ = _seed_project(db)
        result = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "all_rooms"}, db)
        assert result.created_count == 2
        assert result.skipped_count == 1
    finally:
        db.rollback()
        db.close()


def test_project_aggregate_creates_one_project_level_item():
    db = SessionLocal()
    try:
        project, wt, _, _, _ = _seed_project(db)
        result = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "project_aggregate"}, db)
        assert result.created_count == 1
        item = db.get(ProjectWorkItem, result.created_item_ids[0])
        assert item is not None
        assert item.room_id is None
        assert item.scope_mode == "project"
    finally:
        db.rollback()
        db.close()


def test_missing_geometry_room_is_skipped_with_warning():
    db = SessionLocal()
    try:
        project, wt, _, _, r3 = _seed_project(db)
        result = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "selected_rooms", "selected_room_ids": [r3.id]}, db)
        assert result.created_count == 0
        assert result.skipped_count == 1
        assert any("missing_geometry" in warning for warning in result.warnings)
    finally:
        db.rollback()
        db.close()


def test_duplicate_guard_skip_same_work_in_room():
    db = SessionLocal()
    try:
        project, wt, r1, _, _ = _seed_project(db)
        first = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "single_room", "room_id": r1.id}, db)
        assert first.created_count == 1
        second = apply_work_item_to_scope(
            project.id,
            {
                "work_type_id": wt.id,
                "scope_apply_mode": "single_room",
                "room_id": r1.id,
                "duplicate_mode": "skip_same_work_in_room",
            },
            db,
        )
        assert second.created_count == 0
        assert any("duplicate_skipped" in warning for warning in second.warnings)
    finally:
        db.rollback()
        db.close()



def test_all_rooms_reapply_replaces_group_without_duplicates():
    db = SessionLocal()
    try:
        project, wt, _, _, _ = _seed_project(db)
        first = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "all_rooms", "layers": "1"}, db)
        second = apply_work_item_to_scope(project.id, {"work_type_id": wt.id, "scope_apply_mode": "all_rooms", "layers": "1"}, db)
        assert first.created_count == 2
        assert second.created_count == 2
        created = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project.id, ProjectWorkItem.work_type_id == wt.id).all()
        assert len(created) == 2
        assert len({item.source_group_ref for item in created}) == 1
    finally:
        db.rollback()
        db.close()
