from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Project
from app.models.cost import CostCategory, ProjectCostItem
from app.models.project import ProjectWorkerAssignment
from app.models.settings import get_or_create_settings
from app.models.worker import Worker

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_edit_cost_item_recalculates_finance():
    login()
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        project = Project(name="Costed project")
        category = CostCategory(code=f"OTHER-{uuid4().hex[:8]}", name_ru="Прочее", name_sv="Övrigt")
        db.add_all([project, category])
        db.commit()
        db.refresh(project)
        cost_item = ProjectCostItem(
            project_id=project.id,
            cost_category_id=category.id,
            title="Initial",
            amount=Decimal("100.00"),
        )
        db.add(cost_item)
        db.commit()
        db.refresh(cost_item)
        project_id = project.id
        cost_id = cost_item.id
        category_id = category.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/costs/{cost_id}/save",
        data={
            "cost_category_id": str(category_id),
            "material_id": "",
            "title": "Updated",
            "amount": "200",
            "comment": "Note",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        updated_cost = db.get(ProjectCostItem, cost_id)
        assert updated_cost.amount == Decimal("200")
        refreshed_project = db.get(Project, project_id)
        assert refreshed_project.total_cost == Decimal("220.00")
    finally:
        db.close()


def test_edit_and_delete_assignment_updates_finance():
    login()
    db = SessionLocal()
    try:
        get_or_create_settings(db)
        project = Project(name="Hours project")
        worker = Worker(name="Tester", hourly_rate=Decimal("200"))
        db.add_all([project, worker])
        db.commit()
        db.refresh(project)
        assignment = ProjectWorkerAssignment(
            project_id=project.id,
            worker_id=worker.id,
            planned_hours=Decimal("4"),
            actual_hours=Decimal("5"),
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        project_id = project.id
        assignment_id = assignment.id
        worker_id = worker.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/hours/{assignment_id}/save",
        data={
            "worker_id": str(worker_id),
            "planned_hours": "8",
            "actual_hours": "10",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        refreshed_assignment = db.get(ProjectWorkerAssignment, assignment_id)
        assert refreshed_assignment.actual_hours == Decimal("10")
        project = db.get(Project, project_id)
        assert project.salary_fund == Decimal("2000.00")
        assert project.employer_taxes == Decimal("628.40")
        assert project.total_salary_cost == Decimal("2628.40")
        assert project.total_cost == Decimal("2891.24")
    finally:
        db.close()

    delete_response = client.post(
        f"/projects/{project_id}/hours/{assignment_id}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 303

    db = SessionLocal()
    try:
        assert db.get(ProjectWorkerAssignment, assignment_id) is None
        project = db.get(Project, project_id)
        assert project.salary_fund == Decimal("0.00")
        assert project.total_salary_cost == Decimal("0.00")
        assert project.total_cost == Decimal("0.00")
    finally:
        db.close()
