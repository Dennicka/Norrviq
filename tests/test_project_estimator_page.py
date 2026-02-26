from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Estimator page {uuid4().hex[:6]}")
        room = Room(project=project, name="R", floor_area_m2=Decimal("12"), wall_area_m2=Decimal("30"), ceiling_area_m2=Decimal("12"), wall_perimeter_m=Decimal("14"))
        wt = WorkType(code=f"W-{uuid4().hex[:4]}", name_ru="Покраска", name_sv="Paint", category="paint", unit="m2", hours_per_unit=Decimal("0.2"), is_active=True)
        item = ProjectWorkItem(project=project, room=room, work_type=wt, scope_mode="PROJECT", basis_type="floor_area_m2", pricing_mode="HOURLY", hourly_rate_ex_vat=Decimal("500"), quantity=Decimal("1"), difficulty_factor=Decimal("1"))
        db.add_all([project, room, wt, item])
        db.commit()
        return project.id
    finally:
        db.close()


def test_estimator_page_get_and_recalculate_updates_calculated_fields():
    _login()
    pid = _seed()
    page = client.get(f"/projects/{pid}/estimator")
    assert page.status_code == 200

    recalc = client.post(f"/projects/{pid}/estimator/recalculate", data={}, follow_redirects=False)
    assert recalc.status_code == 303

    db = SessionLocal()
    try:
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == pid).first()
        assert item is not None
        assert Decimal(str(item.calculated_qty or 0)) > 0
        assert Decimal(str(item.calculated_hours or 0)) > 0
        assert Decimal(str(item.calculated_sell_ex_vat or 0)) > 0
    finally:
        db.close()
