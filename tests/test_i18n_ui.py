import re

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Client, Project

client = TestClient(app)
settings = get_settings()


def _csrf_token(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m
    return m.group(1)


def _login() -> None:
    page = client.get("/login")
    if "csrf_token" not in page.text:
        return
    token = _csrf_token(page.text)
    response = client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def _project_id() -> int:
    db = SessionLocal()
    try:
        c = Client(name="I18N UI Client")
        db.add(c)
        db.flush()
        p = Project(name="I18N UI Project", client_id=c.id, status="draft")
        db.add(p)
        db.commit()
        return p.id
    finally:
        db.close()


def test_ru_pages_have_localized_labels_without_obvious_english_leakage():
    anon = TestClient(app)
    login_page = anon.get("/login?lang=ru")
    assert "Вход в систему" in login_page.text
    assert "Login" not in login_page.text

    _login()
    project_id = _project_id()

    projects_page = client.get("/projects/?lang=ru")
    assert "Проекты" in projects_page.text
    assert "Save" not in projects_page.text

    project_page = client.get(f"/projects/{project_id}?lang=ru")
    assert "Проект" in project_page.text

    estimator_page = client.get(f"/projects/{project_id}/estimator?lang=ru")
    assert "Смета проекта" in estimator_page.text
    assert "Массовые действия" in estimator_page.text
    assert "Bulk actions" not in estimator_page.text
    assert "Pricing options" not in estimator_page.text

    clients_page = client.get("/clients/?lang=ru")
    assert "Клиенты" in clients_page.text

    settings_page = client.get("/settings/company?lang=ru")
    assert settings_page.status_code == 200
    assert "Компания" in settings_page.text


def test_sv_and_en_samples_render_expected_labels():
    _login()

    sv_page = client.get("/projects/?lang=sv")
    assert "Projekt" in sv_page.text

    en_page = client.get("/projects/?lang=en")
    assert "Projects" in en_page.text


def test_language_switcher_preserves_current_path():
    _login()
    response = client.get("/projects/?lang=ru")
    assert response.status_code == 200
    assert "/lang/en?next=/projects/%3Flang%3Dru" in response.text

def test_ru_key_pages_do_not_render_hardcoded_english_labels():
    _login()
    project_id = _project_id()

    buffer_rules_page = client.get('/web/buffer-rules?lang=ru')
    assert buffer_rules_page.status_code == 200
    assert 'Буферные правила' in buffer_rules_page.text
    assert 'Buffer rules' not in buffer_rules_page.text
    assert 'Rule #' not in buffer_rules_page.text

    pricing_policy_page = client.get('/settings/pricing-policy?lang=ru')
    assert pricing_policy_page.status_code == 200
    assert 'Политика цен' in pricing_policy_page.text
    assert 'Pricing policy' not in pricing_policy_page.text
    assert 'Minimum margin %' not in pricing_policy_page.text

    project_buffers_page = client.get(f'/projects/{project_id}/buffers?lang=ru')
    assert project_buffers_page.status_code == 200
    assert 'Буферы проекта' in project_buffers_page.text
    assert 'Project buffers' not in project_buffers_page.text
    assert 'Speed profile' not in project_buffers_page.text
