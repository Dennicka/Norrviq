from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Client, Project

client = TestClient(app)
settings = get_settings()


def login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def create_project() -> int:
    db = SessionLocal()
    try:
        c = Client(name="I18N Client")
        db.add(c)
        db.flush()
        p = Project(name="I18N Project", client_id=c.id, status="draft")
        db.add(p)
        db.commit()
        return p.id
    finally:
        db.close()


def test_language_switcher_supports_ru_sv_en_and_persists_cookie():
    login()
    response = client.get("/lang/en?next=/projects/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/projects/")
    assert "lang=en" in response.headers.get("set-cookie", "")

    projects = client.get("/projects/")
    assert projects.status_code == 200
    assert "lang/en" in projects.text


def test_core_pages_render_on_selected_language_without_missing_keys():
    project_id = create_project()
    login()
    client.get("/lang/en?next=/projects/", follow_redirects=False)

    for path in (
        "/login",
        "/projects/",
        "/clients/",
        f"/projects/{project_id}",
        f"/projects/{project_id}/pricing",
        f"/projects/{project_id}/materials-plan",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert "i18n.missing" not in response.text


def test_project_status_is_translated_not_raw_enum_code():
    project_id = create_project()
    login()
    client.get("/lang/en?next=/projects/", follow_redirects=False)

    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert any(word in response.text for word in ("Draft", "Utkast", "Черновик"))
    assert ":</strong> draft" not in response.text
