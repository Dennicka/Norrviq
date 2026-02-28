from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal, engine
from app.main import app
from app.models.material import Material
from app.models.material_norm import MaterialConsumptionNorm
from app.models.project import Project, ProjectWorkItem
from app.models.room import Room
from app.models.supplier import Supplier
from app.models.supplier_material_price import SupplierMaterialPrice
from app.models.worktype import WorkType
from tests.utils.sql_count import count_sql_statements


client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_large_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Perf wizard {uuid4().hex[:6]}")
        db.add(project)
        db.flush()

        work_type = WorkType(
            code=f"perf-{uuid4().hex[:8]}",
            category="prep",
            unit="m2",
            name_ru="Покраска",
            name_sv="Målning",
            hours_per_unit=Decimal("0.5"),
            is_active=True,
        )
        db.add(work_type)
        db.flush()

        material = Material(
            code=f"MAT-{uuid4().hex[:8]}",
            name_ru="Краска",
            name_sv="Färg",
            unit="l",
            is_active=True,
            pack_size=Decimal("10"),
            pack_unit="l",
            default_cost_per_unit_ex_vat=Decimal("50"),
            default_sell_per_unit_ex_vat=Decimal("80"),
        )
        db.add(material)
        db.flush()

        supplier = Supplier(name=f"Supplier {uuid4().hex[:6]}")
        db.add(supplier)
        db.flush()
        db.add(
            SupplierMaterialPrice(
                supplier_id=supplier.id,
                material_id=material.id,
                pack_size=Decimal("10"),
                pack_unit="l",
                pack_price_ex_vat=Decimal("500"),
                currency="SEK",
            )
        )

        db.add(
            MaterialConsumptionNorm(
                name="Perf norm",
                material_name="Краска",
                material_category="PAINT",
                applies_to_work_type=work_type.code,
                work_kind=work_type.code,
                active=True,
                is_active=True,
                consumption_value=Decimal("0.2"),
                consumption_unit="per_1_m2",
                material_unit="l",
                waste_percent=Decimal("10"),
                default_unit_price_sek=Decimal("60"),
            )
        )

        rooms: list[Room] = []
        for i in range(30):
            room = Room(
                project_id=project.id,
                name=f"Room {i + 1}",
                floor_area_m2=Decimal("20"),
                wall_perimeter_m=Decimal("18"),
                wall_height_m=Decimal("2.6"),
                wall_area_m2=Decimal("46.8"),
                ceiling_area_m2=Decimal("20"),
            )
            rooms.append(room)
            db.add(room)
        db.flush()

        for i in range(20):
            db.add(
                ProjectWorkItem(
                    project_id=project.id,
                    room_id=rooms[i % len(rooms)].id,
                    work_type_id=work_type.id,
                    quantity=Decimal("20"),
                    calculated_qty=Decimal("20"),
                    calculated_hours=Decimal("10"),
                    scope_mode="room",
                    basis_type="floor_area_m2",
                )
            )

        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_rooms_query_count_reasonable():
    _login()
    project_id = _seed_large_project()

    with count_sql_statements(engine) as counter:
        response = client.get(f"/projects/{project_id}/wizard?step=rooms&lang=ru")

    assert response.status_code == 200
    assert counter.total <= 80


def test_wizard_pricing_query_count_reasonable():
    _login()
    project_id = _seed_large_project()

    with count_sql_statements(engine) as counter:
        response = client.get(f"/projects/{project_id}/wizard?step=pricing&lang=en")

    assert response.status_code == 200
    assert counter.total <= 90


def test_wizard_materials_query_count_reasonable():
    _login()
    project_id = _seed_large_project()

    with count_sql_statements(engine) as counter:
        response = client.get(f"/projects/{project_id}/wizard?step=materials&lang=sv")

    assert response.status_code == 200
    assert counter.total <= 100


def test_wizard_documents_query_count_reasonable():
    _login()
    project_id = _seed_large_project()

    with count_sql_statements(engine) as counter:
        response = client.get(f"/projects/{project_id}/wizard?step=documents&lang=en")

    assert response.status_code == 200
    assert counter.total <= 80
