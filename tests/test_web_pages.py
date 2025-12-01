from datetime import date

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Project

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_analytics_page_shows_project():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Analytics Project", planned_start_date=date(2024, 1, 1))
        db.add(project)
        db.commit()
        db.refresh(project)
    finally:
        db.close()

    response = client.get("/analytics/")
    assert response.status_code == 200
    assert "Analytics Project" in response.text


def test_help_page_available():
    login()
    response = client.get("/help/")
    assert response.status_code == 200
    assert "Справка" in response.text or "Hjälp" in response.text
