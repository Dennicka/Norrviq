import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

client = TestClient(app)


def _login_admin() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "workspace-admin@example.com").first():
            db.add(User(email="workspace-admin@example.com", password_hash=hash_password("Password#123"), role="admin"))
            db.commit()
    finally:
        db.close()
    client.post("/login", data={"username": "workspace-admin@example.com", "password": "Password#123"})


def _project_id() -> int:
    db = SessionLocal()
    try:
        c = Client(name=f"Workspace Client {uuid.uuid4()}")
        db.add(c)
        db.commit()
        db.refresh(c)
        p = Project(name=f"Workspace Project {uuid.uuid4()}", client_id=c.id, status="draft")
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_workspace_tabs_render_and_tab_query_works():
    _login_admin()
    project_id = _project_id()
    response = client.get(f"/projects/{project_id}?tab=pricing")
    assert response.status_code == 200
    assert "projects.workspace.tab.pricing" not in response.text
    assert 'class="active">Политика цен<' in response.text
    assert 'data-tab="pricing"' in response.text


def test_workspace_recalculate_redirect_preserves_tab():
    _login_admin()
    project_id = _project_id()
    response = client.post(f"/projects/{project_id}/recalculate?tab=scope", data={}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/projects/{project_id}?tab=scope")


def test_workspace_summary_and_help_icons_present():
    _login_admin()
    project_id = _project_id()
    response = client.get(f"/projects/{project_id}?tab=overview")
    assert response.status_code == 200
    assert "Резюме проекта" in response.text
    assert "projects.workspace.summary.total_ex" not in response.text
    assert "help-popover" in response.text
