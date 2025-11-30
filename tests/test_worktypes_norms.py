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


def test_minutes_property_from_hours():
    wt = WorkType(
        code="TEST_PROP",
        category="test",
        unit="piece",
        name_ru="Тест",
        name_sv="Test",
        description_ru=None,
        description_sv=None,
        hours_per_unit=Decimal("1.5"),
        base_difficulty_factor=Decimal("1.0"),
        is_active=True,
    )

    assert wt.minutes_per_unit == 90


def test_set_minutes_updates_hours():
    wt = WorkType(
        code="TEST_SET",
        category="test",
        unit="piece",
        name_ru="Тест",
        name_sv="Test",
        description_ru=None,
        description_sv=None,
        hours_per_unit=Decimal("0"),
        base_difficulty_factor=Decimal("1.0"),
        is_active=True,
    )

    wt.set_minutes_per_unit(45)
    assert float(wt.hours_per_unit) == 0.75


def test_web_form_saves_minutes_as_hours():
    login()
    code = "WEB_FORM_MINUTES"

    db = SessionLocal()
    try:
        existing = db.query(WorkType).filter_by(code=code).first()
        if existing:
            db.delete(existing)
            db.commit()
    finally:
        db.close()

    response = client.post(
        "/worktypes/new",
        data={
            "code": code,
            "category": "test",
            "unit": "m2",
            "name_ru": "Тест",
            "name_sv": "Test",
            "description_ru": "",
            "description_sv": "",
            "minutes_per_unit": "90",
            "base_difficulty_factor": "1",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    db = SessionLocal()
    try:
        wt = db.query(WorkType).filter_by(code=code).first()
        assert wt is not None
        assert round(float(wt.hours_per_unit), 2) == round(Decimal("90") / Decimal(60), 2)
    finally:
        db.close()
