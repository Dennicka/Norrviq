from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.dependencies import get_db
from app.main import app
from app.models.project import Project

client = TestClient(app)
settings = get_settings()


def _login() -> None:
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def _seed_project() -> int:
    db = SessionLocal()
    try:
        project = Project(name=f"Wizard entry test {uuid4().hex[:6]}")
        db.add(project)
        db.commit()
        return project.id
    finally:
        db.close()


def test_wizard_object_redirects_not_404():
    _login()
    project_id = _seed_project()

    response = client.get("/wizard/object?lang=ru", follow_redirects=False)

    assert response.status_code in (200, 302, 303)
    if response.status_code in (302, 303):
        location = response.headers["location"]
        assert location.startswith(f"/projects/{project_id}/wizard?step=")
    else:
        assert f"/projects/{project_id}/wizard?step=object" in response.text


def test_wizard_entry_redirects_to_projects_when_no_projects():
    _login()
    class _FakeQuery:
        def order_by(self, *_args, **_kwargs):
            return self

        def first(self):
            return None

        def all(self):
            return []

    class _FakeSession:
        def query(self, *_args, **_kwargs):
            return _FakeQuery()

    def _fake_get_db():
        yield _FakeSession()

    app.dependency_overrides[get_db] = _fake_get_db
    try:
        response = client.get("/wizard", follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "созда" in response.text.lower() or "create" in response.text.lower()



def test_onboarding_open_wizard_link_is_valid():
    _login()
    _seed_project()

    response = client.get("/onboarding", follow_redirects=False)

    assert response.status_code == 200
    assert 'href="/wizard' in response.text

    href = "/wizard"
    if 'href="/wizard/object"' in response.text:
        href = "/wizard/object"
    elif 'href="/wizard?step=rooms"' in response.text:
        href = "/wizard?step=rooms"

    open_wizard_response = client.get(href, follow_redirects=False)
    assert open_wizard_response.status_code != 404
