from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.invoice import Invoice
from app.models.project import Project
from app.models.settings import get_or_create_settings
from app.services.finance import compute_project_finance

router = APIRouter(prefix="/projects/{project_id}/invoices", tags=["invoices"])

INVOICE_STATUSES = ["draft", "sent", "paid", "overdue", "cancelled"]


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _get_project(db: Session, project_id: int) -> Project:
    project = (
        db.query(Project)
        .options(selectinload(Project.client))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_invoice(db: Session, project_id: int, invoice_id: int) -> Invoice:
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.project))
        .filter(Invoice.id == invoice_id, Invoice.project_id == project_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/", response_class=HTMLResponse)
async def list_invoices(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.client), selectinload(Project.invoices))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    invoices = sorted(
        project.invoices,
        key=lambda inv: inv.issue_date or date.min,
        reverse=True,
    )

    context = template_context(request, lang)
    context.update({"project": project, "invoices": invoices})
    return templates.TemplateResponse("invoices/list.html", context)


@router.get("/create", response_class=HTMLResponse)
async def create_invoice_form(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = _get_project(db, project_id)
    settings = get_or_create_settings(db)
    finance_summary = compute_project_finance(db, project, settings=settings)

    defaults = {
        "invoice_number": "",
        "issue_date": date.today(),
        "due_date": None,
        "status": "draft",
        "work_sum_without_moms": finance_summary.work_sum_without_moms,
        "moms_amount": finance_summary.moms_amount,
        "rot_amount": finance_summary.rot_amount,
        "client_pays_total": finance_summary.client_pays_total,
        "comment": "",
    }

    context = template_context(request, lang)
    context.update(
        {
            "project": project,
            "invoice": None,
            "statuses": INVOICE_STATUSES,
            "defaults": defaults,
            "action_url": f"/projects/{project.id}/invoices/create",
        }
    )
    return templates.TemplateResponse("invoices/form.html", context)


@router.post("/create")
async def create_invoice(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
):
    project = _get_project(db, project_id)
    form = await request.form()

    invoice_number = form.get("invoice_number")
    if not invoice_number:
        raise HTTPException(status_code=400, detail="Invoice number required")

    invoice = Invoice(
        project_id=project.id,
        invoice_number=invoice_number,
        issue_date=_parse_date(form.get("issue_date")) or date.today(),
        due_date=_parse_date(form.get("due_date")),
        paid_date=_parse_date(form.get("paid_date")),
        status=form.get("status") if form.get("status") in INVOICE_STATUSES else "draft",
        work_sum_without_moms=Decimal(form.get("work_sum_without_moms") or "0"),
        moms_amount=Decimal(form.get("moms_amount") or "0"),
        rot_amount=Decimal(form.get("rot_amount") or "0"),
        client_pays_total=Decimal(form.get("client_pays_total") or "0"),
        comment=form.get("comment"),
    )

    db.add(invoice)
    db.commit()

    return RedirectResponse(
        url=f"/projects/{project.id}/invoices/", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{invoice_id}/edit", response_class=HTMLResponse)
async def edit_invoice_form(
    project_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    project = _get_project(db, project_id)
    invoice = _get_invoice(db, project_id, invoice_id)

    context = template_context(request, lang)
    context.update(
        {
            "project": project,
            "invoice": invoice,
            "statuses": INVOICE_STATUSES,
            "defaults": None,
            "action_url": f"/projects/{project.id}/invoices/{invoice.id}/edit",
        }
    )
    return templates.TemplateResponse("invoices/form.html", context)


@router.post("/{invoice_id}/edit")
async def update_invoice(
    project_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    form = await request.form()

    invoice.invoice_number = form.get("invoice_number") or invoice.invoice_number
    invoice.issue_date = _parse_date(form.get("issue_date")) or invoice.issue_date
    invoice.due_date = _parse_date(form.get("due_date"))
    invoice.paid_date = _parse_date(form.get("paid_date"))
    invoice.status = (
        form.get("status") if form.get("status") in INVOICE_STATUSES else invoice.status
    )
    invoice.work_sum_without_moms = Decimal(form.get("work_sum_without_moms") or "0")
    invoice.moms_amount = Decimal(form.get("moms_amount") or "0")
    invoice.rot_amount = Decimal(form.get("rot_amount") or "0")
    invoice.client_pays_total = Decimal(form.get("client_pays_total") or "0")
    invoice.comment = form.get("comment")

    db.add(invoice)
    db.commit()

    return RedirectResponse(
        url=f"/projects/{project_id}/invoices/", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{invoice_id}/delete")
async def delete_invoice(
    project_id: int,
    invoice_id: int,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    db.delete(invoice)
    db.commit()

    return RedirectResponse(
        url=f"/projects/{project_id}/invoices/", status_code=status.HTTP_303_SEE_OTHER
    )
