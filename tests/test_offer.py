from decimal import Decimal
import uuid

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.project import Project, ProjectWorkItem
from app.models.worktype import WorkType

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def create_project_with_data():
    db = SessionLocal()
    try:
        test_client = Client(name="Test Client", address="Test Street", is_rot_eligible=True)
        db.add(test_client)
        db.commit()
        db.refresh(test_client)

        wt_code = f"WT-{uuid.uuid4()}"
        work_type = WorkType(
            code=wt_code,
            category="paint",
            unit="h",
            name_ru="Покраска",
            description_ru="Покраска стен",
            name_sv="Målning",
            description_sv="Målning av väggar",
            hours_per_unit=Decimal("1.0"),
            base_difficulty_factor=Decimal("1.0"),
        )
        db.add(work_type)
        db.commit()
        db.refresh(work_type)

        project = Project(
            name="Test Project",
            client_id=test_client.id,
            address="Test Address",
            use_rot=True,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        item = ProjectWorkItem(
            project_id=project.id,
            work_type_id=work_type.id,
            quantity=Decimal("10"),
            difficulty_factor=Decimal("1.0"),
        )
        db.add(item)
        db.commit()

        project_id = project.id
        return project_id
    finally:
        db.close()


def test_offer_page_requires_auth():
    response = client.get("/projects/1/offer", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


def test_offer_page_works_for_authenticated_user():
    project_id = create_project_with_data()
    login()
    response = client.get(f"/projects/{project_id}/offer?lang=sv")
    assert response.status_code == 200
    assert "Test Client" in response.text or "Test Project" in response.text
    assert "Offertvillkor" in response.text
