from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, Project, ProjectPricing, ProjectWorkItem, Room, WorkType

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_invoice_create_form_post():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Invoice Form Project {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/invoices/create",
        data={
            "issue_date": date.today().isoformat(),
            "status": "draft",
            "work_sum_without_moms": "100.00",
            "moms_amount": "25.00",
            "rot_amount": "0.00",
            "client_pays_total": "125.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        created = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        assert created is not None
        assert created.invoice_number is None
        assert created.project_id == project_id
    finally:
        db.close()


def test_project_add_work_item_form_post():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Work Item Project {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-FORM-{uuid4().hex[:8]}",
            category="test",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            description_ru="",
            description_sv="",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"))
        db.add_all([project, worktype, room])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        db.refresh(room)
        project_id = project.id
        worktype_id = worktype.id
        room_id = room.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(worktype_id),
            "quantity": "10",
            "difficulty_factor": "1.20",
            "comment": "from form",
            "scope_mode": "room",
            "room_id": str(room_id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        item = (
            db.query(ProjectWorkItem)
            .filter(ProjectWorkItem.project_id == project_id)
            .order_by(ProjectWorkItem.id.desc())
            .first()
        )
        assert item is not None
        assert item.work_type_id == worktype_id
    finally:
        db.close()


def test_project_add_work_item_legacy_apply_to_selected_room_without_room_is_rejected():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Legacy Work Item Project {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-LEGACY-{uuid4().hex[:8]}",
            category="test",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            description_ru="",
            description_sv="",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"))
        db.add_all([project, worktype, room])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        db.refresh(room)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(worktype_id),
            "apply_to": "selected_room",
            "quantity": "7",
            "difficulty_factor": "1.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
        assert items_count == 0
    finally:
        db.close()


def test_worktype_create_form_post():
    login()
    code = f"WT-NEW-{uuid4().hex[:8]}"

    response = client.post(
        "/worktypes/new",
        data={
            "code": code,
            "category": "test",
            "unit": "m2",
            "name_ru": "Новый тип работ",
            "name_sv": "Ny arbetstyp",
            "description_ru": "",
            "description_sv": "",
            "minutes_per_unit": "90",
            "base_difficulty_factor": "1.00",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        created = db.query(WorkType).filter(WorkType.code == code).first()
        assert created is not None
        assert created.minutes_per_unit == 90
    finally:
        db.close()


def test_add_work_item_hidden_pricing_fields_do_not_fail():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Pricing Hidden Fields {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-HIDDEN-{uuid4().hex[:8]}",
            category="wall",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"))
        db.add_all([project, worktype, room])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        db.refresh(room)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(worktype_id),
            "quantity": "5",
            "difficulty_factor": "1.0",
            "pricing_mode": "hourly",
            "hourly_rate_sek": "550",
            "area_rate_sek": "",
            "fixed_price_sek": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_add_work_item_invalid_pricing_mode_does_not_create_item():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Invalid Pricing {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-INVALID-{uuid4().hex[:8]}",
            category="test",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"))
        db.add_all([project, worktype, room])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        db.refresh(room)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(worktype_id), "quantity": "5", "pricing_mode": "bad_mode"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
        assert items_count == 0
    finally:
        db.close()


def test_add_work_item_fixed_mode_requires_fixed_price():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Fixed Pricing {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-FIXED-{uuid4().hex[:8]}",
            category="test",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        room = Room(project=project, name="Kitchen", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"))
        db.add_all([project, worktype, room])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        db.refresh(room)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(worktype_id), "quantity": "5", "pricing_mode": "fixed"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
        assert items_count == 0
    finally:
        db.close()


def test_project_add_work_item_project_scope_without_room_id():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Project Scope Item {uuid4().hex[:8]}")
        room1 = Room(project=project, name="A", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("14"), wall_height_m=Decimal("2.5"))
        room2 = Room(project=project, name="B", floor_area_m2=Decimal("20"), wall_perimeter_m=Decimal("18"), wall_height_m=Decimal("2.5"))
        worktype = WorkType(
            code=f"WT-PROJECT-{uuid4().hex[:8]}",
            category="wall",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        db.add_all([project, room1, room2, worktype])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(worktype_id),
            "scope_mode": "project",
            "difficulty_factor": "1.0",
            "layers": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        item = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).order_by(ProjectWorkItem.id.desc()).first()
        assert item is not None
        assert item.room_id is None
        assert item.scope_mode == "project"
        assert Decimal(str(item.quantity)) == Decimal("80.00")
    finally:
        db.close()


def test_project_scope_validation_without_rooms_shows_error():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Empty Project Scope {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-EMPTY-{uuid4().hex[:8]}",
            category="wall",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        db.add_all([project, worktype])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(worktype_id), "scope_mode": "project"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
        assert items_count == 0
    finally:
        db.close()


def test_room_scope_validation_without_room_id_shows_error():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Missing Room Scope {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-NOROOM-{uuid4().hex[:8]}",
            category="wall",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        db.add_all([project, worktype])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={"work_type_id": str(worktype_id), "scope_mode": "room", "quantity": "5"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        items_count = db.query(ProjectWorkItem).filter(ProjectWorkItem.project_id == project_id).count()
        assert items_count == 0
    finally:
        db.close()


def test_project_page_displays_aggregated_hours_summary():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Totals View {uuid4().hex[:8]}")
        room = Room(project=project, name="A", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("14"), wall_height_m=Decimal("2.5"))
        worktype = WorkType(
            code=f"WT-TOTALS-{uuid4().hex[:8]}",
            category="paint",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        item1 = ProjectWorkItem(project=project, room=room, scope_mode="room", work_type=worktype, quantity=Decimal("2"), difficulty_factor=Decimal("1"), calculated_hours=Decimal("2"), pricing_mode="hourly", hourly_rate_sek=Decimal("500"), calculated_cost_without_moms=Decimal("1000"))
        item2 = ProjectWorkItem(project=project, scope_mode="project", room_id=None, work_type=worktype, quantity=Decimal("3"), difficulty_factor=Decimal("1"), calculated_hours=Decimal("3"), pricing_mode="hourly", hourly_rate_sek=Decimal("500"), calculated_cost_without_moms=Decimal("1500"))
        db.add_all([project, room, worktype, item1, item2])
        db.commit()
        project_id = project.id
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert "Общие часы" in response.text


def test_project_pricing_mode_form_saves_mode_and_values():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Pricing Settings {uuid4().hex[:8]}")
        pricing = ProjectPricing(project=project)
        db.add_all([project, pricing])
        db.commit()
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/estimator-pricing-mode",
        data={
            "project_pricing_mode": "per_m2",
            "sqm_rate": "195",
            "sqm_basis": "walls_ceilings",
            "include_materials_in_sell_price": "1",
            "currency": "SEK",
            "rounding_mode": "none",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert pricing.pricing_mode == "per_m2"
        assert Decimal(str(pricing.sqm_rate)) == Decimal("195.00")
        assert pricing.sqm_basis == "walls_ceilings"
    finally:
        db.close()


def test_project_page_shows_pricing_summary_block():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Pricing Summary {uuid4().hex[:8]}")
        room = Room(project=project, name="A", floor_area_m2=Decimal("10"), wall_perimeter_m=Decimal("12"), wall_height_m=Decimal("2.5"))
        worktype = WorkType(code=f"WT-SUM-{uuid4().hex[:8]}", category="paint", unit="m2", name_ru="Тест", name_sv="Test", hours_per_unit=Decimal("1.00"), base_difficulty_factor=Decimal("1.0"), is_active=True)
        item = ProjectWorkItem(project=project, room=room, work_type=worktype, quantity=Decimal("2"), difficulty_factor=Decimal("1"), calculated_hours=Decimal("2"))
        pricing = ProjectPricing(project=project, pricing_mode="per_m2", sqm_rate=Decimal("195"), sqm_basis="walls_ceilings")
        db.add_all([project, room, worktype, item, pricing])
        db.commit()
        project_id = project.id
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert "Режим ценообразования" in response.text
    assert "Hourly preview" in response.text
    assert "Per m² preview" in response.text
    assert "Fixed preview" in response.text


def test_project_pricing_mode_form_validation_rejects_invalid_payload():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Pricing Validation {uuid4().hex[:8]}")
        pricing = ProjectPricing(project=project)
        db.add_all([project, pricing])
        db.commit()
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/estimator-pricing-mode",
        data={"project_pricing_mode": "fixed", "fixed_price_amount": "-10"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        assert pricing is not None
        assert (pricing.pricing_mode or "hourly") != "fixed"
    finally:
        db.close()
