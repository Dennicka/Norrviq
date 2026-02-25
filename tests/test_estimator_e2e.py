from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.worktype import WorkType

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed() -> tuple[int, int]:
    db = SessionLocal()
    try:
        project = Project(name=f"E2E Estimator {uuid4().hex[:8]}")
        rooms = [
            Room(project=project, name="R1", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5")),
            Room(project=project, name="R2", floor_area_m2=Decimal("12"), wall_perimeter_m=Decimal("13"), wall_height_m=Decimal("2.5")),
            Room(project=project, name="R3", floor_area_m2=Decimal("8"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2.5")),
        ]
        wt = WorkType(code=f"FLOOR-PROT-{uuid4().hex[:5]}", category="floor protection", unit="m2", name_ru="Защита пола", name_sv="Golvskydd", hours_per_unit=Decimal("0.1"), is_active=True)
        mat = Material(code=f"PAPER-{uuid4().hex[:5]}", name_ru="Бумага", name_sv=f"Paper-{uuid4().hex[:5]}", unit="m2", default_price_per_unit=Decimal("1"), is_active=True)
        norm = MaterialConsumptionNorm(applies_to_work_type=wt.code, material_name=mat.name_sv, material_category="consumable", material_unit="m2", consumption_value=Decimal("1"), consumption_unit="per_m2", surface_type="floor", active=True)
        db.add_all([project, wt, mat, norm, *rooms])
        db.commit()
        return project.id, wt.id
    finally:
        db.close()


def test_estimator_e2e_all_rooms_totals_compare_materials():
    _login()
    project_id, wt_id = _seed()
    res = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(wt_id), "scope_mode": "all_rooms", "difficulty_factor": "1", "layers": "1"},
        follow_redirects=False,
    )
    assert res.status_code == 303

    db = SessionLocal()
    try:
        qty_sum = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).with_entities(ProjectWorkItem.quantity).all()
        assert sum((Decimal(str(row[0])) for row in qty_sum), Decimal("0")) == Decimal("30.00")
    finally:
        db.close()

    page = client.get(f"/projects/{project_id}/estimator")
    assert page.status_code == 200
    assert 'data-testid="totals"' in page.text
    assert 'data-testid="pricing_table"' in page.text
    assert 'data-testid="materials_plan"' in page.text
    assert 'data-testid="scope_badge"' in page.text
