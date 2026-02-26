from decimal import Decimal
from uuid import uuid4

from app.db import SessionLocal
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.materials_bom import compute_project_bom


def test_missing_norm_emits_warning_without_crash():
    db = SessionLocal()
    try:
        project = Project(name=f"Warn-{uuid4().hex[:6]}")
        wt = WorkType(code=f"wt-{uuid4().hex[:5]}", category="wall", unit="m2", name_ru="", name_sv="", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        db.add_all([project, wt])
        db.flush()
        room = Room(project_id=project.id, name="R", floor_area_m2=Decimal("5"), wall_area_m2=Decimal("15"), ceiling_area_m2=Decimal("5"))
        db.add(room)
        db.flush()
        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")))
        db.commit()

        bom = compute_project_bom(db, project.id)
        assert any("MISSING_NORM" in warning for warning in bom.warnings)
    finally:
        db.close()
