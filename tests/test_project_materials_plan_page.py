from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.user import User
from app.models.worktype import WorkType
from app.security import hash_password


client = TestClient(app)


def _login():
    db = SessionLocal()
    try:
        email = f"materials-{uuid4().hex[:6]}@example.com"
        db.add(User(email=email, password_hash=hash_password("Pass#123456"), role="admin"))
        db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": "Pass#123456", "next": "/projects/"}, follow_redirects=False)


def test_materials_plan_page_and_recalc_endpoint():
    _login()
    db = SessionLocal()
    try:
        project = Project(name=f"Proj-{uuid4().hex[:6]}")
        wt = WorkType(code=f"wt-{uuid4().hex[:4]}", category="wall", unit="m2", name_ru="", name_sv="", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        db.add_all([project, wt])
        db.flush()
        room = Room(project_id=project.id, name="R", wall_area_m2=Decimal("20"), floor_area_m2=Decimal("10"), ceiling_area_m2=Decimal("10"))
        db.add(room)
        db.flush()
        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")))
        db.add(MaterialConsumptionNorm(active=True, is_active=True, material_name="Putty", material_category="putty", applies_to_work_type=wt.code, work_type_code=wt.code, basis_type="wall_area_m2", surface_type="wall", consumption_qty=Decimal("1"), per_basis_qty=Decimal("10"), layers_multiplier_enabled=False, waste_factor_pct=Decimal("0"), consumption_value=Decimal("1"), consumption_unit="per_10_m2", material_unit="KG", default_unit_price_sek=Decimal("100"), waste_percent=Decimal("0")))
        db.commit()
        pid = project.id
    finally:
        db.close()

    response = client.get(f"/projects/{pid}/materials-plan")
    assert response.status_code == 200
    assert "Putty" in response.text

    recalc = client.post(f"/projects/{pid}/materials-plan/recalc", follow_redirects=False)
    assert recalc.status_code == 303
