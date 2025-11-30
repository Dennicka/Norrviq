from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_clients_page():
    response = client.get("/clients/")
    assert response.status_code == 200


def test_worktypes_page():
    response = client.get("/worktypes/")
    assert response.status_code == 200


def test_projects_page():
    response = client.get("/projects/")
    assert response.status_code == 200
