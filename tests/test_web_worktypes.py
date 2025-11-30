from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.worktype import WorkType

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def ensure_worktype(code: str, hours: Decimal = Decimal("1.50")) -> WorkType:
    db = SessionLocal()
    try:
        wt = db.query(WorkType).filter_by(code=code).first()
        if not wt:
            wt = WorkType(
                code=code,
                category="test",
                unit="m2",
                name_ru="Тест",
                name_sv="Test",
                description_ru="",
                description_sv="",
                hours_per_unit=hours,
                base_difficulty_factor=Decimal("1.0"),
                is_active=True,
            )
            db.add(wt)
        else:
            wt.hours_per_unit = hours
        db.commit()
        db.refresh(wt)
        return wt
    finally:
        db.close()


def delete_worktype(code: str) -> None:
    db = SessionLocal()
    try:
        wt = db.query(WorkType).filter_by(code=code).first()
        if wt:
            db.delete(wt)
            db.commit()
    finally:
        db.close()


def test_list_shows_minutes_and_hours():
    login()
    wt = ensure_worktype("LIST_WT", hours=Decimal("1.50"))

    response = client.get("/worktypes/")
    assert response.status_code == 200
    assert "90 (1.50)" in response.text
    delete_worktype(wt.code)


def test_copy_button_creates_new_worktype():
    login()
    source_code = "COPY_SOURCE"
    copy_code = "COPY_TARGET"

    delete_worktype(source_code)
    delete_worktype(copy_code)
    wt = ensure_worktype(source_code, hours=Decimal("1.25"))

    copy_form = client.get(f"/worktypes/{wt.id}/copy")
    assert copy_form.status_code == 200
    assert f"{source_code}_copy" in copy_form.text

    response = client.post(
        "/worktypes/new",
        data={
            "code": copy_code,
            "category": wt.category,
            "unit": wt.unit,
            "name_ru": wt.name_ru,
            "name_sv": wt.name_sv,
            "description_ru": wt.description_ru or "",
            "description_sv": wt.description_sv or "",
            "minutes_per_unit": wt.minutes_per_unit,
            "base_difficulty_factor": wt.base_difficulty_factor,
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    db = SessionLocal()
    try:
        copied = db.query(WorkType).filter_by(code=copy_code).first()
        assert copied is not None
        assert copied.minutes_per_unit == wt.minutes_per_unit
    finally:
        db.close()
        delete_worktype(source_code)
        delete_worktype(copy_code)
