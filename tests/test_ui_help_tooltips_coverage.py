from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.project import Project

from app.ui.help_registry import HELP_TEXT


REQUIRED_HELP_KEYS = {
    "takeoff.include_openings_subtraction",
    "takeoff.paintable_basis",
    "pricing.modes",
    "pricing.apply_best_mode",
    "pricing.floor_min_effective_hourly",
    "pricing.margin_profit_explained",
    "materials.waste_percent",
    "procurement.rounding_mode",
    "procurement.min_packs",
    "procurement.pack_multiple",
    "procurement.unit_mismatch_warning",
    "documents.issue_freeze_explained",
    "documents.print_vs_pdf",
}


def test_help_registry_has_required_tooltip_keys_and_languages():
    missing = sorted(REQUIRED_HELP_KEYS - set(HELP_TEXT))
    assert not missing
    for key in REQUIRED_HELP_KEYS:
        for lang in ("ru", "sv", "en"):
            assert HELP_TEXT[key].get(lang)



client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post("/login", data={"username": settings.admin_username, "password": settings.admin_password})


def _seed_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Wizard help {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_pricing_has_help_icons():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}/wizard?step=pricing&lang=en")
    assert response.status_code == 200
    assert 'data-help-key="pricing.modes"' in response.text
    assert 'data-help-key="pricing.apply_best_mode"' in response.text
    assert 'data-help-key="pricing.floor_min_effective_hourly"' in response.text
    assert response.text.count('data-help-key="') >= 3


def test_wizard_materials_has_help_icons():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}/wizard?step=materials&lang=sv")
    assert response.status_code == 200
    assert 'data-help-key="procurement.rounding_mode"' in response.text
    assert (
        'data-help-key="procurement.unit_mismatch_warning"' in response.text
        or 'data-help-key="procurement.rounding_mode"' in response.text
    )


def test_documents_step_has_issue_and_print_help():
    _login()
    project_id = _seed_project()

    response = client.get(f"/projects/{project_id}/wizard?step=documents&lang=ru")
    assert response.status_code == 200
    assert 'data-help-key="documents.issue_freeze_explained"' in response.text
    assert 'data-help-key="documents.print_vs_pdf"' in response.text
    assert response.text.count('data-help-key="') >= 2
