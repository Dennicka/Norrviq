from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def _login() -> None:
    settings = get_settings()
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/materials/norms"},
        follow_redirects=False,
    )


def test_material_norms_contains_help_tip_markers():
    _login()
    response = client.get("/materials/norms/create?lang=ru")
    assert response.status_code == 200

    for help_key in [
        "materials_norms.basis_type",
        "materials_norms.consumption_qty",
        "materials_norms.per_basis_qty",
        "materials_norms.per_basis_unit",
        "materials_norms.layers_multiplier",
        "materials_norms.waste_percent",
    ]:
        assert f'data-help="{help_key}"' in response.text
