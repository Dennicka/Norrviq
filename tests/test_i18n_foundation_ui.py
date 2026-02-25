import re

from fastapi.testclient import TestClient

from app.config import get_settings
from app.i18n import get_translation
from app.main import app


def _csrf_token(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m
    return m.group(1)


def _login(client: TestClient) -> None:
    settings = get_settings()
    page = client.get("/login")
    token = _csrf_token(page.text)
    response = client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def test_i18n_fallback_missing_key_goes_to_en_then_key():
    assert get_translation("ru", "menu.projects") == "Проекты"
    assert get_translation("ru", "menu.company") == "Компания"
    assert get_translation("ru", "totally.missing.key") == "totally.missing.key"


def test_language_switch_cookie_persists_after_reload():
    with TestClient(app) as client:
        _login(client)
        switch = client.get("/lang/en?next=/settings/pricing-policy", follow_redirects=False)
        assert switch.status_code in (302, 307)
        assert "lang=en" in switch.headers.get("set-cookie", "")

        page = client.get("/settings/pricing-policy")
        assert page.status_code == 200
        assert "Pricing policy" in page.text


def test_ru_smoke_pricing_and_buffer_rules_pages_render_without_500():
    with TestClient(app) as client:
        _login(client)
        client.get("/lang/ru?next=/", follow_redirects=False)

        pricing = client.get("/settings/pricing-policy")
        assert pricing.status_code == 200
        assert "Политика цен" in pricing.text
        assert "Minimum margin" not in pricing.text

        buffer_rules = client.get("/web/buffer-rules")
        assert buffer_rules.status_code == 200
        assert "Буферные правила" in buffer_rules.text
        assert "No rules" not in buffer_rules.text
