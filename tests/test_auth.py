from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.db import SessionLocal
from app.models.user import User
from app.security import hash_password, validate_security_settings, verify_password
from app.services.auth import create_admin_user


client = TestClient(app)
settings = get_settings()


def _ensure_admin(email: str = "admin@test.local", password: str = "StrongAdmin#123"):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            create_admin_user(db, email=email, password=password)
    finally:
        db.close()
    return email, password


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
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    get_settings.cache_clear()

    try:
        try:
            validate_security_settings()
            assert False, "Expected validate_security_settings to fail without SESSION_SECRET"
        except RuntimeError as exc:
            assert "SESSION_SECRET" in str(exc)
    finally:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("SESSION_SECRET", "test-secret-key-0123456789-0123456789")
        get_settings.cache_clear()


def test_default_admin_admin_login_fails():
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin", "next": "/projects/"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "class=\"error\"" in response.text


def test_login_logout_session_rotation():
    email, password = _ensure_admin()
    anon_response = client.get("/login")
    anon_cookie = anon_response.headers.get("set-cookie", "")

    login_response = client.post(
        "/login",
        data={"username": email, "password": password, "next": "/projects/"},
        follow_redirects=False,
    )
    assert login_response.status_code in (302, 303)
    login_cookie = login_response.headers.get("set-cookie", "")
    assert settings.session_cookie_name in login_cookie
    assert anon_cookie != login_cookie

    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code in (302, 303)

    response_after_logout = client.get("/projects/", follow_redirects=False)
    assert response_after_logout.status_code in (302, 307)
    assert "/login" in response_after_logout.headers.get("location", "")


def test_session_cookie_hardening_flags():
    response = client.get("/login")
    cookie = response.headers.get("set-cookie", "")
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    if settings.cookie_secure:
        assert "secure" in lowered


def test_create_admin_user_hashes_password():
    email = "bootstrap-admin@example.com"
    password = "VerySecure#Pass123"
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            db.delete(existing)
            db.commit()

        user = create_admin_user(db, email=email, password=password)
        assert user.password_hash != password
        assert verify_password(password, user.password_hash)
    finally:
        db.close()


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
