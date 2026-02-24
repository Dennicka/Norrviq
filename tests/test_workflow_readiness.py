from decimal import Decimal

from app.db import SessionLocal
from app.models import CompanyProfile, Project, ProjectPricing, ProjectWorkItem, Room, WorkType
from app.services.workflow import build_project_workflow_state


def test_workflow_readiness_empty_project_blocked():
    db = SessionLocal()
    try:
        project = Project(name="WF empty")
        db.add(project)
        db.commit()
        state = build_project_workflow_state(db, project.id, lang="ru")
        statuses = {s["key"]: s["status"] for s in state["steps"]}
        assert statuses["rooms_works"] == "blocked"
        assert statuses["estimate_pricing"] == "blocked"
    finally:
        db.close()


def test_workflow_readiness_rooms_only_warning_or_blocked():
    db = SessionLocal()
    try:
        project = Project(name="WF rooms")
        db.add(project)
        db.flush()
        db.add(Room(project_id=project.id, name="A"))
        db.commit()
        state = build_project_workflow_state(db, project.id, lang="ru")
        statuses = {s["key"]: s["status"] for s in state["steps"]}
        assert statuses["rooms_works"] in {"warning", "blocked"}
        assert statuses["offer"] == "blocked"
    finally:
        db.close()


def test_workflow_readiness_with_works_and_pricing_ready_for_offer():
    db = SessionLocal()
    try:
        profile = db.query(CompanyProfile).first()
        if profile:
            profile.org_number = "556677-8899"
            profile.vat_number = "SE556677889901"
        project = Project(name="WF ready")
        db.add(project)
        db.flush()
        room = Room(project_id=project.id, name="A", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.4"))
        wt = WorkType(code=f"WF-{project.id}", unit="m2", name_ru="Покраска", name_sv="Paint", hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"))
        db.add_all([room, wt])
        db.flush()
        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("5"), calculated_hours=Decimal("5"), difficulty_factor=Decimal("1")))
        db.add(ProjectPricing(project_id=project.id, mode="HOURLY", hourly_rate_override=Decimal("450")))
        db.commit()

        state = build_project_workflow_state(db, project.id, lang="ru")
        statuses = {s["key"]: s["status"] for s in state["steps"]}
        assert statuses["estimate_pricing"] in {"done", "warning"}
        assert statuses["offer"] in {"done", "warning"}
    finally:
        db.close()
