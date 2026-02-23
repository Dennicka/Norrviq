from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.material import Material
from app.models.material_recipe import MaterialRecipe
from app.models.paint_system import PaintSystem, PaintSystemStep, PaintSystemSurface, ProjectPaintSettings, RoomPaintSettings
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
    db.query(PaintSystemStep).delete()
    db.query(RoomPaintSettings).delete()
    db.query(ProjectPaintSettings).delete()
    db.query(PaintSystem).delete()
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
    assert "materials" in response.text.lower()


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


def test_paint_system_applies_steps_by_surface_area():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        primer = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Грунт", name_sv="Primer", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("10.00"))
        top = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Краска", name_sv="Paint", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("10.00"))
        db.add_all([primer, top])
        db.flush()
        r1 = MaterialRecipe(name="PrimerR", material_id=primer.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE")
        r2 = MaterialRecipe(name="TopR", material_id=top.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=2, waste_pct=Decimal("0"), rounding_mode="NONE")
        db.add_all([r1, r2])
        db.flush()
        ps = PaintSystem(name=f"Walls-{uuid4().hex[:4]}", version=1, is_active=True)
        db.add(ps)
        db.flush()
        db.add_all([
            PaintSystemStep(paint_system_id=ps.id, step_order=1, target_surface=PaintSystemSurface.WALLS, recipe_id=r1.id),
            PaintSystemStep(paint_system_id=ps.id, step_order=2, target_surface=PaintSystemSurface.WALLS, recipe_id=r2.id),
        ])
        db.add(ProjectPaintSettings(project_id=project_id, default_wall_paint_system_id=ps.id))
        db.commit()
        bom = compute_project_bom(db, project_id)
        qtys = {i.name: i.qty_required_unit for i in bom.items}
        assert qtys["Primer"] == Decimal("3.0000")
        assert qtys["Paint"] == Decimal("6.0000")
    finally:
        db.close()


def test_room_override_system_wins_over_project_default():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        room = db.query(Room).filter(Room.project_id == project_id).first()
        m1 = Material(code=f"M-{uuid4().hex[:6]}", name_ru="A", name_sv="A", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("1.00"))
        m2 = Material(code=f"M-{uuid4().hex[:6]}", name_ru="B", name_sv="B", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("1.00"))
        db.add_all([m1, m2])
        db.flush()
        rr1 = MaterialRecipe(name="R1", material_id=m1.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE")
        rr2 = MaterialRecipe(name="R2", material_id=m2.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.2"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE")
        db.add_all([rr1, rr2])
        db.flush()
        s1 = PaintSystem(name=f"S-{uuid4().hex[:4]}", version=1, is_active=True)
        s2 = PaintSystem(name=f"S-{uuid4().hex[:4]}", version=1, is_active=True)
        db.add_all([s1, s2])
        db.flush()
        db.add_all([
            PaintSystemStep(paint_system_id=s1.id, step_order=1, target_surface=PaintSystemSurface.WALLS, recipe_id=rr1.id),
            PaintSystemStep(paint_system_id=s2.id, step_order=1, target_surface=PaintSystemSurface.WALLS, recipe_id=rr2.id),
        ])
        db.add(ProjectPaintSettings(project_id=project_id, default_wall_paint_system_id=s1.id))
        db.add(RoomPaintSettings(room_id=room.id, wall_paint_system_id=s2.id))
        db.commit()
        bom = compute_project_bom(db, project_id)
        assert [i.name for i in bom.items] == ["B"]
    finally:
        db.close()


def test_bom_aggregates_same_material_across_rooms():
    db = SessionLocal()
    try:
        p = Project(name=f"Agg-{uuid4().hex[:6]}")
        db.add(p)
        db.flush()
        r1 = Room(project_id=p.id, name="R1", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2"), wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"))
        r2 = Room(project_id=p.id, name="R2", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("10"), wall_height_m=Decimal("2"), wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"))
        db.add_all([r1, r2])
        db.flush()
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="X", name_sv="X", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("1.00"))
        db.add(m)
        db.flush()
        rr = MaterialRecipe(name="RX", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE")
        db.add(rr)
        db.flush()
        s1 = PaintSystem(name=f"AA-{uuid4().hex[:4]}", version=1, is_active=True)
        db.add(s1)
        db.flush()
        db.add(PaintSystemStep(paint_system_id=s1.id, step_order=1, target_surface=PaintSystemSurface.WALLS, recipe_id=rr.id))
        db.add(ProjectPaintSettings(project_id=p.id, default_wall_paint_system_id=s1.id))
        db.commit()
        bom = compute_project_bom(db, p.id)
        assert len(bom.items) == 1
        assert bom.items[0].qty_required_unit == Decimal("4.0000")
    finally:
        db.close()


def test_project_paint_settings_page_assigns_systems():
    _login("paint-operator@example.com", "operator")
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        s = PaintSystem(name=f"UI-{uuid4().hex[:4]}", version=1, is_active=True)
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()
    response = client.post(f"/projects/{project_id}/paint-settings", data={"default_wall_paint_system_id": str(sid)}, follow_redirects=False)
    assert response.status_code == 303


def test_bom_changes_when_system_assigned():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="C", name_sv="C", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("1.00"))
        db.add(m)
        db.flush()
        rr = MaterialRecipe(name="RC", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE")
        db.add(rr)
        db.flush()
        bom_before = compute_project_bom(db, project_id)
        s = PaintSystem(name=f"BB-{uuid4().hex[:4]}", version=1, is_active=True)
        db.add(s)
        db.flush()
        db.add(PaintSystemStep(paint_system_id=s.id, step_order=1, target_surface=PaintSystemSurface.CEILING, recipe_id=rr.id))
        db.add(ProjectPaintSettings(project_id=project_id, default_ceiling_paint_system_id=s.id))
        db.commit()
        bom_after = compute_project_bom(db, project_id)
        assert bom_before.total_cost_ex_vat != bom_after.total_cost_ex_vat
    finally:
        db.close()


def test_admin_only_settings_paint_systems_and_operator_project_room_paint_settings_csrf():
    _login("paint-viewer@example.com", "viewer")
    assert client.get("/settings/paint-systems").status_code == 403

    _login("paint-admin@example.com", "admin")
    assert client.get("/settings/paint-systems").status_code == 200

    project_id, _ = _seed_project()
    _login("paint-operator2@example.com", "operator")
    ok = client.post(f"/projects/{project_id}/paint-settings", data={}, follow_redirects=False)
    assert ok.status_code == 303
    no_csrf = client.post(f"/projects/{project_id}/paint-settings", data={}, headers={"X-No-Auto-CSRF": "1"}, follow_redirects=False)
    assert no_csrf.status_code == 403


def test_bom_golden_case_with_paint_system_single_room_walls_ceiling():
    project_id, _ = _seed_project()
    db = SessionLocal()
    try:
        _clear_material_recipes(db)
        m = Material(code=f"M-{uuid4().hex[:6]}", name_ru="Gold", name_sv="Gold", unit="L", is_active=True, default_cost_per_unit_ex_vat=Decimal("100.00"))
        db.add(m)
        db.flush()
        rr = MaterialRecipe(name="GoldR", material_id=m.id, applies_to="PROJECT", basis="WALL_AREA", consumption_per_m2=Decimal("0.1"), coats_count=1, waste_pct=Decimal("0"), rounding_mode="NONE")
        db.add(rr)
        db.flush()
        s = PaintSystem(name=f"GoldS-{uuid4().hex[:4]}", version=1, is_active=True)
        db.add(s)
        db.flush()
        db.add_all([
            PaintSystemStep(paint_system_id=s.id, step_order=1, target_surface=PaintSystemSurface.WALLS, recipe_id=rr.id),
            PaintSystemStep(paint_system_id=s.id, step_order=2, target_surface=PaintSystemSurface.CEILING, recipe_id=rr.id),
        ])
        db.add(ProjectPaintSettings(project_id=project_id, default_wall_paint_system_id=s.id, default_ceiling_paint_system_id=s.id))
        db.commit()
        bom = compute_project_bom(db, project_id)
        assert str(bom.items[0].qty_required_unit) == "4.0000"
        assert str(bom.total_cost_ex_vat) == "400.00"
    finally:
        db.close()
