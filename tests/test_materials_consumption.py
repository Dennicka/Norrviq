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
from app.services.materials_consumption import calculate_material_needs_for_project

client = TestClient(app)


def _login_admin(email: str = "materials-rules-admin@example.com", password: str = "Pass#123456"):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, password_hash=hash_password(password), role="admin"))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": email, "password": password, "next": "/materials/rules"}, follow_redirects=False)


def _seed_project_with_rooms() -> tuple[int, int, int, int]:
    db = SessionLocal()
    try:
        project = Project(name=f"MC-{uuid4().hex[:6]}")
        wt_ceiling = WorkType(code=f"paint_ceiling_{uuid4().hex[:4]}", category="paint", unit="m2", name_ru="Покраска потолка", name_sv="Ceiling paint", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        wt_wall = WorkType(code=f"paint_wall_{uuid4().hex[:4]}", category="paint", unit="m2", name_ru="Покраска стен", name_sv="Wall paint", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        wt_misc = WorkType(code=f"misc_{uuid4().hex[:4]}", category="misc", unit="m2", name_ru="Другое", name_sv="Other", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        db.add_all([project, wt_ceiling, wt_wall, wt_misc])
        db.flush()
        r1 = Room(project_id=project.id, name="R1", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("20"), ceiling_area_m2=Decimal("10"), wall_perimeter_m=Decimal("14"))
        r2 = Room(project_id=project.id, name="R2", floor_area_m2=Decimal("5"), wall_area_m2=Decimal("12"), ceiling_area_m2=Decimal("5"), wall_perimeter_m=Decimal("10"))
        db.add_all([r1, r2])
        db.flush()
        db.add_all([
            ProjectWorkItem(project_id=project.id, room_id=r1.id, work_type_id=wt_ceiling.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")),
            ProjectWorkItem(project_id=project.id, room_id=r1.id, work_type_id=wt_wall.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")),
            ProjectWorkItem(project_id=project.id, room_id=None, work_type_id=wt_wall.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")),
            ProjectWorkItem(project_id=project.id, room_id=r2.id, work_type_id=wt_misc.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")),
        ])
        db.commit()
        return project.id, wt_ceiling.id, wt_wall.id, wt_misc.id
    finally:
        db.close()


def test_rule_crud_form_post_create():
    _login_admin()
    response = client.post(
        "/materials/rules/new",
        data={
            "is_active": "on",
            "material_name": "Ceiling paint white",
            "material_category": "paint",
            "work_kind": "painting_ceiling",
            "basis_type": "ceiling_area",
            "quantity_per_basis": "0.3",
            "basis_unit": "m2",
            "material_unit": "l",
            "waste_factor_pct": "10",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db = SessionLocal()
    try:
        row = db.query(MaterialConsumptionNorm).filter(MaterialConsumptionNorm.material_name == "Ceiling paint white").first()
        assert row is not None
        assert row.work_kind == "painting_ceiling"
    finally:
        db.close()


def test_ceiling_paint_calculation():
    project_id, *_ = _seed_project_with_rooms()
    db = SessionLocal()
    try:
        db.add(MaterialConsumptionNorm(material_name="Ceiling paint", material_category="paint", applies_to_work_type="painting_ceiling", work_kind="painting_ceiling", basis_type="ceiling_area", quantity_per_basis=Decimal("0.3"), basis_unit="m2", material_unit="l", waste_factor_pct=Decimal("0"), consumption_value=Decimal("0.3"), waste_percent=Decimal("0"), consumption_unit="per_1_m2", active=True, is_active=True))
        db.commit()
        _, totals = calculate_material_needs_for_project(db, project_id)
        total = next(t for t in totals if t.material_name == "Ceiling paint")
        assert total.total_quantity == Decimal("3.0000")
    finally:
        db.close()


def test_wall_paint_uses_wall_area_not_floor():
    project_id, *_ = _seed_project_with_rooms()
    db = SessionLocal()
    try:
        db.add(MaterialConsumptionNorm(material_name="Wall paint", material_category="paint", applies_to_work_type="painting_walls", work_kind="painting_walls", basis_type="wall_area", quantity_per_basis=Decimal("0.2"), basis_unit="m2", material_unit="l", waste_factor_pct=Decimal("0"), consumption_value=Decimal("0.2"), waste_percent=Decimal("0"), consumption_unit="per_1_m2", active=True, is_active=True))
        db.commit()
        rows, _ = calculate_material_needs_for_project(db, project_id)
        first_room_row = next(r for r in rows if r.material_name == "Wall paint" and r.basis_quantity == Decimal("20.0000"))
        assert first_room_row.calculated_quantity == Decimal("4.0000")
    finally:
        db.close()


def test_project_wide_aggregation_across_rooms():
    project_id, *_ = _seed_project_with_rooms()
    db = SessionLocal()
    try:
        db.add(MaterialConsumptionNorm(material_name="Primer", material_category="primer", applies_to_work_type="painting_walls", work_kind="painting_walls", basis_type="wall_area", quantity_per_basis=Decimal("0.1"), basis_unit="m2", material_unit="l", waste_factor_pct=Decimal("0"), consumption_value=Decimal("0.1"), waste_percent=Decimal("0"), consumption_unit="per_1_m2", active=True, is_active=True))
        db.commit()
        _, totals = calculate_material_needs_for_project(db, project_id)
        total = next(t for t in totals if t.material_name == "Primer")
        assert total.total_quantity == Decimal("5.2000")  # 20 from room item + 32 project wide
    finally:
        db.close()


def test_selected_rooms_scope_uses_only_target_room():
    project_id, *_ = _seed_project_with_rooms()
    db = SessionLocal()
    try:
        db.add(MaterialConsumptionNorm(material_name="Putty", material_category="putty", applies_to_work_type="painting_walls", work_kind="painting_walls", basis_type="wall_area", quantity_per_basis=Decimal("0.5"), basis_unit="m2", material_unit="bucket", waste_factor_pct=Decimal("0"), consumption_value=Decimal("0.5"), waste_percent=Decimal("0"), consumption_unit="per_1_m2", active=True, is_active=True))
        db.commit()
        rows, _ = calculate_material_needs_for_project(db, project_id)
        targeted = [r for r in rows if r.material_name == "Putty" and r.source_work_item_id]
        assert any(r.basis_quantity == Decimal("20.0000") for r in targeted)
    finally:
        db.close()


def test_no_matching_rules_returns_empty_rows():
    db = SessionLocal()
    try:
        project = Project(name=f"NoRule-{uuid4().hex[:6]}")
        wt_misc = WorkType(code=f"unmatched_{uuid4().hex[:4]}", category="misc", unit="m2", name_ru="Другое", name_sv="Other", description_ru=None, description_sv=None, hours_per_unit=Decimal("1"), base_difficulty_factor=Decimal("1"), is_active=True)
        db.add_all([project, wt_misc])
        db.flush()
        room = Room(project_id=project.id, name="R", floor_area_m2=Decimal("10"), wall_area_m2=Decimal("10"), ceiling_area_m2=Decimal("10"))
        db.add(room)
        db.flush()
        db.add(ProjectWorkItem(project_id=project.id, room_id=room.id, work_type_id=wt_misc.id, quantity=Decimal("1"), difficulty_factor=Decimal("1")))
        db.commit()
        rows, totals = calculate_material_needs_for_project(db, project.id)
        assert rows == []
        assert totals == []
    finally:
        db.close()


def test_invalid_rule_input_returns_form_error():
    _login_admin("materials-rules-admin2@example.com")
    response = client.post(
        "/materials/rules/new",
        data={
            "material_name": "Broken",
            "work_kind": "painting_walls",
            "basis_type": "bad_basis",
            "quantity_per_basis": "-1",
            "basis_unit": "m2",
            "material_unit": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "Ошибка валидации" in response.text
