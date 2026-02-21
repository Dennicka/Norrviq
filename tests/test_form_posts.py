from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, Project, ProjectWorkItem, WorkType

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_invoice_create_form_post():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Invoice Form Project {uuid4().hex[:8]}")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/invoices/create",
        data={
            "issue_date": date.today().isoformat(),
            "status": "draft",
            "work_sum_without_moms": "100.00",
            "moms_amount": "25.00",
            "rot_amount": "0.00",
            "client_pays_total": "125.00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        created = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        assert created is not None
        assert created.invoice_number is None
        assert created.project_id == project_id
    finally:
        db.close()


def test_project_add_work_item_form_post():
    login()
    db = SessionLocal()
    try:
        project = Project(name=f"Work Item Project {uuid4().hex[:8]}")
        worktype = WorkType(
            code=f"WT-FORM-{uuid4().hex[:8]}",
            category="test",
            unit="m2",
            name_ru="Тест",
            name_sv="Test",
            description_ru="",
            description_sv="",
            hours_per_unit=Decimal("1.00"),
            base_difficulty_factor=Decimal("1.0"),
            is_active=True,
        )
        db.add_all([project, worktype])
        db.commit()
        db.refresh(project)
        db.refresh(worktype)
        project_id = project.id
        worktype_id = worktype.id
    finally:
        db.close()

    response = client.post(
        f"/projects/{project_id}/add-work-item",
        data={
            "work_type_id": str(worktype_id),
            "quantity": "10",
            "difficulty_factor": "1.20",
            "comment": "from form",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        item = (
            db.query(ProjectWorkItem)
            .filter(ProjectWorkItem.project_id == project_id)
            .order_by(ProjectWorkItem.id.desc())
            .first()
        )
        assert item is not None
        assert item.work_type_id == worktype_id
    finally:
        db.close()


def test_worktype_create_form_post():
    login()
    code = f"WT-NEW-{uuid4().hex[:8]}"

    response = client.post(
        "/worktypes/new",
        data={
            "code": code,
            "category": "test",
            "unit": "m2",
            "name_ru": "Новый тип работ",
            "name_sv": "Ny arbetstyp",
            "description_ru": "",
            "description_sv": "",
            "minutes_per_unit": "90",
            "base_difficulty_factor": "1.00",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        created = db.query(WorkType).filter(WorkType.code == code).first()
        assert created is not None
        assert created.minutes_per_unit == 90
    finally:
        db.close()
