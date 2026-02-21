from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.user import User
from app.security import hash_password, validate_security_settings, verify_password
from app.db import SessionLocal


client = TestClient(app)
settings = get_settings()


def test_login_page_returns_200():
    response = client.get("/login")
    assert response.status_code == 200


def test_password_hashing():
    password = "S3cur3-Password!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_env_required_in_prod(monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_DEFAULTS", "false")
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    get_settings.cache_clear()

    try:
        try:
            validate_security_settings()
            assert False, "Expected validate_security_settings to fail without APP_SECRET_KEY"
        except RuntimeError as exc:
            assert "APP_SECRET_KEY" in str(exc)
    finally:
        monkeypatch.setenv("ALLOW_DEV_DEFAULTS", "true")
        monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-0123456789-0123456789")
        get_settings.cache_clear()


def test_login_logout_session_rotation():
    login_response_1 = client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )
    assert login_response_1.status_code in (302, 303)
    first_cookie = login_response_1.headers.get("set-cookie", "")
    assert settings.session_cookie_name in first_cookie

    login_response_2 = client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )
    second_cookie = login_response_2.headers.get("set-cookie", "")
    assert first_cookie != second_cookie

    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code in (302, 303)

    response_after_logout = client.get("/projects/", follow_redirects=False)
    assert response_after_logout.status_code in (302, 307)
    assert "/login" in response_after_logout.headers.get("location", "")


def test_settings_requires_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "viewer@example.com").first():
            db.add(User(email="viewer@example.com", password_hash=hash_password("viewer-password"), role="viewer"))
            db.commit()
    finally:
        db.close()

    client.get("/logout")
    login_response = client.post(
        "/login",
        data={"username": "viewer@example.com", "password": "viewer-password", "next": "/settings/"},
        follow_redirects=False,
    )
    assert login_response.status_code in (302, 303)

    response = client.get("/settings/", follow_redirects=False)
    assert response.status_code == 403
