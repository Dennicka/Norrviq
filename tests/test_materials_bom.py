from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_recipe import MaterialRecipe
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.user import User
from app.models.worktype import WorkType
from app.security import hash_password
from app.services.materials_bom import compute_project_bom

client = TestClient(app)


def _login(email: str, role: str, password: str = "Pass#123456"):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password(password), role=role))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": password, "next": "/projects/"}, follow_redirects=False)


def _seed_project() -> tuple[int, int]:
    db = SessionLocal()
    try:
        p = Project(name=f"BOM-{uuid4().hex[:6]}")
        wt = WorkType(
            code=f"BOM-WT-{uuid4().hex[:6]}",
            category="paint",
            unit="m2",
            name_ru="Покраска",
            name_sv="Painting",
            description_ru=None,
            description_sv=None,
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.00"),
            is_active=True,
        )
        db.add_all([p, wt])
        db.flush()
        room = Room(
            project_id=p.id,
            name="Room",
            floor_area_m2=Decimal("10.00"),
            wall_perimeter_m=Decimal("12.00"),
            wall_height_m=Decimal("2.50"),
        )
        db.add(room)
        db.flush()
        db.add(ProjectWorkItem(project_id=p.id, room_id=room.id, work_type_id=wt.id, quantity=Decimal("1.00"), difficulty_factor=Decimal("1.00"), calculated_hours=Decimal("1.00"), calculated_cost_without_moms=Decimal("1.00")))
        db.commit()
        return p.id, wt.id
    finally:
        db.close()


def _clear_material_recipes(db):
    db.query(MaterialRecipe).delete()
    db.commit()


def test_bom_qty_formula_with_coats_and_waste():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("100.00"))
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.10"), coats_count=2, waste_pct=Decimal("8.00"), rounding_mode="NONE"))
        db.commit()

        bom = compute_project_bom(db, project_id)
        assert bom.items[0].qty_required_unit == Decimal("6.4800")
    finally:
        db.close()


def test_bom_rounding_ceil_to_packs():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", is_active=True, default_pack_size=Decimal("10.00"), default_cost_per_unit_ex_vat=Decimal("10.00"))
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.10"), coats_count=2, waste_pct=Decimal("8.00"), rounding_mode="CEIL_TO_PACKS"))
        db.commit()

        bom = compute_project_bom(db, project_id)
        assert bom.items[0].packs_count == 1
        assert bom.items[0].qty_final_unit == Decimal("10.0000")
    finally:
        db.close()


def test_bom_uses_recipe_basis_area():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Грунт", name_sv="Primer", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("50.00"))
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Primer", material_id=m.id, applies_to="PROJECT", basis="CEILING_AREA", consumption_per_m2=Decimal("0.20"), coats_count=1, waste_pct=Decimal("0.00"), rounding_mode="NONE"))
        db.commit()
        bom = compute_project_bom(db, project_id)
        assert bom.items[0].area_m2_used == Decimal("10.0000")
    finally:
        db.close()


def test_materials_plan_page_renders_bom():
    _login("bom-viewer@example.com", "viewer")
    project_id, _ = _seed_project()
    response = client.get(f"/projects/{project_id}/materials-plan")
    assert response.status_code == 200
    assert "Materials plan" in response.text


def test_apply_bom_creates_project_cost_items():
    _login("bom-admin@example.com", "admin")
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("10.00"))
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="FLOOR_AREA", consumption_per_m2=Decimal("0.10"), coats_count=1, waste_pct=Decimal("0.00"), rounding_mode="NONE"))
        db.commit()
    finally:
        db.close()

    response = client.post(f"/projects/{project_id}/materials-plan/apply-costs", follow_redirects=False)
    assert response.status_code == 303


def test_apply_bom_requires_role_and_csrf():
    _login("bom-viewer2@example.com", "viewer")
    project_id, _ = _seed_project()
    forbidden = client.post(f"/projects/{project_id}/materials-plan/apply-costs", follow_redirects=False)
    assert forbidden.status_code == 403

    _login("bom-operator@example.com", "operator")
    no_csrf = client.post(
        f"/projects/{project_id}/materials-plan/apply-costs",
        data={},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert no_csrf.status_code == 403


def test_bom_small_room_regression_snapshot_totals():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("100.00"))
        db.add(m)
        db.flush()
        db.add(MaterialRecipe(name="Paint", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.10"), coats_count=2, waste_pct=Decimal("8.00"), rounding_mode="NONE"))
        db.commit()
        bom = compute_project_bom(db, project_id)
        assert str(bom.total_cost_ex_vat) == "648.00"
        assert str(bom.total_sell_ex_vat) == "777.60"
    finally:
        db.close()
