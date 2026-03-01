import json
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Project, ProjectWorkItem, Room, WorkType


client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _ensure_worktype(code: str, name_ru: str, unit: str = "m2") -> None:
    db = SessionLocal()
    try:
        if db.query(WorkType).filter(WorkType.code == code).first():
            return
        db.add(
            WorkType(
                code=code,
                name_ru=name_ru,
                name_sv=name_ru,
                category="paint",
                unit=unit,
                hours_per_unit=Decimal("0.5"),
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_project(with_rooms: int = 0) -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Work pkg {uuid4().hex[:6]}")
        db.add(project)
        db.flush()
        for index in range(with_rooms):
            db.add(
                Room(
                    project_id=project.id,
                    name=f"Room {index + 1}",
                    floor_area_m2=Decimal("10"),
                    wall_area_m2=Decimal("20"),
                    ceiling_area_m2=Decimal("10"),
                    wall_perimeter_m=Decimal("12"),
                )
            )
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_works_shows_package_cards():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}/wizard?step=works&lang=ru")

    assert response.status_code == 200
    assert 'data-pkg-code="PKG_PAINT_WALL_2"' in response.text or "Покраска стен 2 слоя" in response.text


def test_apply_package_is_idempotent_no_duplicates():
    _login()
    _ensure_worktype("PAINT_WALL", "Покраска стен")
    project_id = _seed_project()

    payload = {"package_code": "PKG_PAINT_WALL_2", "scope_mode": "WHOLE_PROJECT"}
    first = client.post(f"/projects/{project_id}/wizard/packages/apply", data=payload, follow_redirects=False)
    second = client.post(f"/projects/{project_id}/wizard/packages/apply", data=payload, follow_redirects=False)

    assert first.status_code == 303
    assert second.status_code == 303

    db = SessionLocal()
    try:
        rows = (
            db.query(ProjectWorkItem)
            .filter(
                ProjectWorkItem.project_id == project_id,
                ProjectWorkItem.source_package_code == "PKG_PAINT_WALL_2",
            )
            .all()
        )
        assert len(rows) == 1
    finally:
        db.close()


def test_remove_package_deletes_only_package_items():
    _login()
    _ensure_worktype("PRIMER_WALL", "Грунт")
    _ensure_worktype("MANUAL_TASK", "Ручная работа")
    project_id = _seed_project()

    db = SessionLocal()
    try:
        manual_type = db.query(WorkType).filter(WorkType.code == "MANUAL_TASK").first()
        db.add(
            ProjectWorkItem(
                project_id=project_id,
                work_type_id=manual_type.id,
                quantity=Decimal("1"),
                difficulty_factor=Decimal("1"),
                scope_mode="WHOLE_PROJECT",
                basis_type="manual_qty",
            )
        )
        db.commit()
    finally:
        db.close()

    client.post(
        f"/projects/{project_id}/wizard/packages/apply",
        data={"package_code": "PKG_PRIMER_WALL", "scope_mode": "WHOLE_PROJECT"},
        follow_redirects=False,
    )
    client.post(
        f"/projects/{project_id}/wizard/packages/remove",
        data={"package_code": "PKG_PRIMER_WALL"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        package_rows = (
            db.query(ProjectWorkItem)
            .filter(ProjectWorkItem.project_id == project_id, ProjectWorkItem.source_package_code == "PKG_PRIMER_WALL")
            .count()
        )
        manual_rows = (
            db.query(ProjectWorkItem)
            .filter(ProjectWorkItem.project_id == project_id, ProjectWorkItem.source_package_code.is_(None))
            .count()
        )
        assert package_rows == 0
        assert manual_rows == 1
    finally:
        db.close()


def test_apply_selected_rooms_scope_persists():
    _login()
    _ensure_worktype("PAINT_CEILING", "Покраска потолка")
    project_id = _seed_project(with_rooms=3)

    db = SessionLocal()
    try:
        rooms = db.query(Room).filter(Room.project_id == project_id).order_by(Room.id.asc()).all()
        selected_ids = [rooms[0].id, rooms[1].id]
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/wizard/packages/apply",
        data={
            "package_code": "PKG_PAINT_CEILING_2",
            "scope_mode": "SELECTED_ROOMS",
            "selected_room_ids": selected_ids,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    db = SessionLocal()
    try:
        row = (
            db.query(ProjectWorkItem)
            .filter(ProjectWorkItem.project_id == project_id, ProjectWorkItem.source_package_code == "PKG_PAINT_CEILING_2")
            .first()
        )
        assert row is not None
        assert sorted(json.loads(row.selected_room_ids_json or "[]")) == sorted(selected_ids)
    finally:
        db.close()
