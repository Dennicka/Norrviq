from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Invoice, InvoiceLine, Project
from app.models.rot_case import RotCase
from app.models.settings import get_or_create_settings
from app.services.invoice_lines import recalculate_invoice_totals

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_create_invoice_and_list():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Invoice project")
        db.add(project)
        db.commit()
        db.refresh(project)
        get_or_create_settings(db)
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
    assert response.status_code in (303, 200)

    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        assert invoice is not None
        assert invoice.client_pays_total == Decimal("125.00")
    finally:
        db.close()

    list_response = client.get(f"/projects/{project_id}/invoices/")
    assert list_response.status_code == 200
    assert "Черновик" in list_response.text or "Utkast" in list_response.text


def test_invoice_page_shows_rot_block_when_enabled():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Invoice rot page")
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    finally:
        db.close()
    client.post(
        f"/projects/{project_id}/invoices/create",
        data={
            "issue_date": date.today().isoformat(),
            "status": "draft",
            "work_sum_without_moms": "100.00",
            "moms_amount": "25.00",
            "rot_amount": "0.00",
            "client_pays_total": "125.00",
        },
    )
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter(Invoice.project_id == project_id).first()
        db.add(RotCase(invoice_id=invoice.id, is_enabled=True, rot_pct=Decimal("30.00")))
        recalculate_invoice_totals(db, invoice.id)
        db.commit()
        invoice_id = invoice.id
    finally:
        db.close()

    response = client.get(f"/projects/{project_id}/invoices/{invoice_id}")
    assert response.status_code == 200
    assert "ROT" in response.text


def test_issued_invoice_rot_snapshot_immutable():
    login()
    db = SessionLocal()
    try:
        project = Project(name="Invoice rot issued")
        db.add(project)
        db.flush()
        invoice = Invoice(
            project_id=project.id,
            issue_date=date.today(),
            status="issued",
            work_sum_without_moms=Decimal("0"),
            moms_amount=Decimal("0"),
            rot_amount=Decimal("10"),
            client_pays_total=Decimal("115"),
            subtotal_ex_vat=Decimal("100"),
            labour_ex_vat=Decimal("100"),
            material_ex_vat=Decimal("0"),
            other_ex_vat=Decimal("0"),
            vat_total=Decimal("25"),
            total_inc_vat=Decimal("125"),
            rot_snapshot_enabled=True,
            rot_snapshot_pct=Decimal("10"),
            rot_snapshot_eligible_labor_ex_vat=Decimal("100"),
            rot_snapshot_amount=Decimal("10"),
        )
        db.add(invoice)
        db.flush()
        db.add(RotCase(invoice_id=invoice.id, is_enabled=True, rot_pct=Decimal("90")))
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                position=1,
                kind="LABOR",
                description="Labor",
                quantity=Decimal("1"),
                unit_price_ex_vat=Decimal("100"),
                vat_rate_pct=Decimal("25"),
                source_type="MANUAL",
            )
        )
        recalculate_invoice_totals(db, invoice.id)
        assert invoice.rot_amount == Decimal("10.00")
        assert invoice.client_pays_total == Decimal("115.00")
    finally:
        db.rollback()
        db.close()
