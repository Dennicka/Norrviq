from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_clients_page():
    login()
    response = client.get("/clients/")
    assert response.status_code == 200


def test_worktypes_page():
    login()
    response = client.get("/worktypes/")
    assert response.status_code == 200


def test_projects_page():
    login()
    response = client.get("/projects/")
    assert response.status_code == 200
