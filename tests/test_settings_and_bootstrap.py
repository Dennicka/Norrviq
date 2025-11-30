from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.cost import CostCategory
from app.models.legal_note import LegalNote
from app.models.settings import get_or_create_settings
from app.services.bootstrap import ensure_default_cost_categories, ensure_default_legal_notes

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_bootstrap_creates_defaults():
    db: Session = SessionLocal()
    try:
        ensure_default_cost_categories(db)
        ensure_default_legal_notes(db)

        codes = {c.code for c in db.query(CostCategory).all()}
        assert {"MATERIALS", "FUEL", "PARKING", "RENT", "OTHER"}.issubset(codes)

        note_codes = {n.code for n in db.query(LegalNote).all()}
        assert {"ROT_BASICS", "MOMS_BASICS"}.issubset(note_codes)
    finally:
        db.close()


def test_settings_page_works():
    login()
    response = client.get("/settings/")
    assert response.status_code == 200

    form_data = {
        "hourly_rate_company": "777.77",
        "default_worker_hourly_rate": "180",
        "employer_contributions_percent": "31.42",
        "moms_percent": "25",
        "rot_percent": "50",
        "fuel_price_per_liter": "20",
        "transport_cost_per_km": "25",
        "default_overhead_percent": "10",
        "default_worker_tax_percent_for_net": "30",
    }
    post_response = client.post("/settings/", data=form_data, follow_redirects=False)
    assert post_response.status_code in (302, 303)

    db: Session = SessionLocal()
    try:
        settings_obj = get_or_create_settings(db)
        assert float(settings_obj.hourly_rate_company) == 777.77
    finally:
        db.close()

    response_after = client.get("/settings/")
    assert "777.77" in response_after.text
