from fastapi.testclient import TestClient

from app.main import app
from app.i18n import get_translation
from app.config import get_settings


client = TestClient(app)
settings = get_settings()


def test_root_page_returns_200_and_contains_header():
    response = client.get("/")
    assert response.status_code == 200
    assert get_translation(settings.default_lang, "index.header") in response.text
