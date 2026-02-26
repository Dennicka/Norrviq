from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def _login() -> None:
    settings = get_settings()
    client.post(
        "/login",
        data={"username": settings.admin_email, "password": settings.admin_password, "next": "/projects/"},
        follow_redirects=False,
    )


def test_nav_is_russian_and_no_key_english_titles_when_lang_ru():
    _login()
    response = client.get("/projects/?lang=ru")
    assert response.status_code == 200

    assert "Проекты" in response.text
    assert "Клиенты" in response.text
    assert "Материалы" in response.text

    assert "Pricing Policy" not in response.text
    assert "Paint systems" not in response.text
