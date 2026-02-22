from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.project import Project, ProjectWorkItem
from app.models.project_pricing import ProjectPricing
from app.models.room import Room
from app.models.worktype import WorkType
from app.services.offer_commercial import compute_offer_commercial

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_project() -> int:
    db = SessionLocal()
    try:
        c = Client(name="Commercial Client")
        db.add(c)
        db.flush()
        p = Project(name="Commercial Project", client_id=c.id, address="Test")
        db.add(p)
        db.flush()
        wt = WorkType(code=f"WT-{p.id}", category="paint", unit="h", name_ru="Работа", name_sv="Arbete", hours_per_unit=Decimal("1.0"), base_difficulty_factor=Decimal("1.0"))
        db.add(wt)
        db.flush()
        db.add(ProjectWorkItem(project_id=p.id, work_type_id=wt.id, quantity=Decimal("10.00"), difficulty_factor=Decimal("1.0"), calculated_hours=Decimal("10.00")))
        db.add(Room(project_id=p.id, name="R1", floor_area_m2=Decimal("20.00"), wall_perimeter_m=Decimal("18"), wall_height_m=Decimal("2.5")))
        db.add(ProjectPricing(project_id=p.id, mode="HOURLY", hourly_rate_override=Decimal("600.00"), fixed_total_price=Decimal("9000.00"), rate_per_m2=Decimal("300.00"), rate_per_room=Decimal("2000.00"), rate_per_piece=Decimal("700.00")))
        db.commit()
        return p.id
    finally:
        db.close()


def test_offer_commercial_totals_match_pricing_scenario_for_each_mode():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        for mode in ("HOURLY", "FIXED_TOTAL", "PER_M2"):
            pricing.mode = mode
            db.commit()
            offer = compute_offer_commercial(db, project_id, lang="sv")
            assert offer.mode == mode
            assert offer.price_ex_vat > Decimal("0")
            assert offer.price_inc_vat == (offer.price_ex_vat + offer.vat_amount)
    finally:
        db.close()


def test_offer_page_uses_commercial_lines_not_workitem_costs_when_fixed():
    project_id = _seed_project()
    db = SessionLocal()
    try:
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        pricing.mode = "FIXED_TOTAL"
        pricing.fixed_total_price = Decimal("12345.00")
        db.commit()
    finally:
        db.close()

    _login()
    response = client.get(f"/projects/{project_id}/offer?lang=sv")
    assert response.status_code == 200
    assert "Fast pris för målning enligt överenskommelse" in response.text
    assert "12345.00" in response.text


def test_offer_issue_snapshots_commercial_and_is_immutable():
    project_id = _seed_project()
    _login()
    r1 = client.post(f"/offers/{project_id}/finalize", data={"terms_lang": "sv"}, follow_redirects=False)
    assert r1.status_code == 303

    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        snapshot = project.offer_commercial_snapshot
        assert snapshot
        pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
        pricing.fixed_total_price = Decimal("1.00")
        db.commit()
    finally:
        db.close()

    page = client.get(f"/projects/{project_id}/offer?lang=sv")
    assert page.status_code == 200
    assert "1.00" not in page.text


def test_offer_issue_blocks_on_mismatch(monkeypatch):
    project_id = _seed_project()
    _login()

    class _Result:
        ok = False
        errors = [{"code": "TOTAL_PRICE_EX_VAT_MISMATCH", "message": "boom"}]

    monkeypatch.setattr("app.services.document_numbering.validate_pricing_consistency", lambda *args, **kwargs: _Result())

    response = client.post(f"/offers/{project_id}/finalize", headers={"accept": "application/json"}, data={"terms_lang": "sv"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Offer totals mismatch pricing scenario"
