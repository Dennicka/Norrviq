from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


client = TestClient(app)
settings = get_settings()


def test_login_page_returns_200():
    response = client.get("/login")
    assert response.status_code == 200


def test_protected_redirects_to_login():
    response = client.get("/projects/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/login" in response.headers.get("location", "")


def test_successful_login_sets_session():
    login_response = client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )
    assert login_response.status_code in (302, 303)
    assert login_response.headers.get("location") == "/projects/"

    authorized_response = client.get("/projects/")
    assert authorized_response.status_code == 200


def test_logout_clears_session():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password, "next": "/projects/"},
    )
    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code in (302, 303)

    response_after_logout = client.get("/projects/", follow_redirects=False)
    assert response_after_logout.status_code in (302, 307)
    assert "/login" in response_after_logout.headers.get("location", "")
