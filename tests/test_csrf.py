import re
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.client import Client
from app.db import SessionLocal

client = TestClient(app)
settings = get_settings()

CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')


def _extract_csrf_token(html: str) -> str:
    match = CSRF_META_RE.search(html)
    assert match is not None
    return match.group(1)


def _login() -> None:
    login_page = client.get("/login")
    token = _extract_csrf_token(login_page.text)
    response = client.post(
        "/login",
        data={
            "username": settings.admin_email,
            "password": settings.admin_password,
            "csrf_token": token,
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def test_csrf_token_generation():
    response = client.get("/login")
    assert response.status_code == 200
    assert _extract_csrf_token(response.text)


def test_csrf_validation_fail():
    _login()
    response = client.post(
        "/clients/new",
        data={"name": f"CSRF Fail {uuid4().hex[:8]}"},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert "CSRF" in response.text


def test_csrf_validation_ok():
    _login()
    form_page = client.get("/clients/")
    token = _extract_csrf_token(form_page.text)

    response = client.post(
        "/clients/new",
        data={"name": f"CSRF OK {uuid4().hex[:8]}", "csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_csrf_integration_create_and_delete_client():
    _login()
    create_page = client.get("/clients/")
    token = _extract_csrf_token(create_page.text)
    client_name = f"CSRF Integration {uuid4().hex[:8]}"

    create_response = client.post(
        "/clients/new",
        data={"name": client_name, "csrf_token": token},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    db = SessionLocal()
    try:
        created_client = db.query(Client).filter(Client.name == client_name).first()
        assert created_client is not None
        client_id = created_client.id
    finally:
        db.close()

    detail_response = client.get(f"/clients/{client_id}")
    delete_token = _extract_csrf_token(detail_response.text)
    delete_response = client.post(
        f"/clients/{client_id}/delete",
        data={"csrf_token": delete_token},
        headers={"X-CSRF-Token": delete_token},
        follow_redirects=False,
    )
    assert delete_response.status_code == 303


def test_csrf_fetch_header_required():
    _login()
    response = client.post(
        "/clients/new",
        json={"name": f"Fetch Fail {uuid4().hex[:8]}"},
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_policy_update_requires_csrf():
    _login()
    response = client.post(
        "/settings/pricing-policy",
        data={
            "min_margin_pct": "20",
            "min_profit_sek": "1500",
            "min_effective_hourly_ex_vat": "600",
        },
        headers={"X-No-Auto-CSRF": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403
