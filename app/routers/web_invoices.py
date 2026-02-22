import logging
from datetime import date
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.dependencies import get_current_lang, get_db, template_context, templates
from app.models.company_profile import get_or_create_company_profile
from app.models.audit_event import AuditEvent
from app.models.invoice_line import InvoiceLine
from app.models.invoice import Invoice
from app.models.project import Project
from app.models.settings import get_or_create_settings
from app.security import ADMIN_ROLE, OPERATOR_ROLE, require_role
from app.services.finance import compute_project_finance
from app.services.invoice_lines import (
    MERGE_APPEND,
    MERGE_REPLACE_ALL,
    MERGE_UPSERT_BY_SOURCE,
    generate_invoice_lines_from_project,
    recalculate_invoice_totals,
)
from app.services.terms_templates import DOC_TYPE_INVOICE, resolve_terms_template

router = APIRouter(prefix="/projects/{project_id}/invoices", tags=["invoices"])

INVOICE_STATUSES = ["draft", "issued", "paid", "overdue", "cancelled"]
logger = logging.getLogger("app.invoices")


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
        .options(selectinload(Invoice.project).selectinload(Project.client))
        .filter(Invoice.id == invoice_id, Invoice.project_id == project_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _ensure_editable(invoice: Invoice) -> None:
    if invoice.status == "issued":
        raise HTTPException(status_code=409, detail="Issued invoice is read-only")


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

    company_profile = get_or_create_company_profile(db)
    context = template_context(request, lang)
    context.update({"project": project, "invoices": invoices, "company_profile": company_profile})
    return templates.TemplateResponse(request, "invoices/list.html", context)


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
    company_profile = get_or_create_company_profile(db)

    defaults = {
        "invoice_number": None,
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
            "company_profile": company_profile,
            "can_edit": True,
        }
    )
    return templates.TemplateResponse(request, "invoices/form.html", context)


@router.post("/create")
async def create_invoice(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    project = _get_project(db, project_id)
    form = await request.form()

    invoice = Invoice(
        project_id=project.id,
        invoice_number=None,
        issue_date=_parse_date(form.get("issue_date")) or date.today(),
        due_date=_parse_date(form.get("due_date")),
        paid_date=_parse_date(form.get("paid_date")),
        status="draft",
        work_sum_without_moms=Decimal(form.get("work_sum_without_moms") or "0"),
        moms_amount=Decimal(form.get("moms_amount") or "0"),
        rot_amount=Decimal(form.get("rot_amount") or "0"),
        client_pays_total=Decimal(form.get("client_pays_total") or "0"),
        comment=form.get("comment"),
    )

    db.add(invoice)
    db.flush()
    work_sum = Decimal(form.get("work_sum_without_moms") or "0")
    moms = Decimal(form.get("moms_amount") or "0")
    vat_rate = Decimal("25.00")
    if work_sum > 0:
        vat_rate = (moms / work_sum * Decimal("100")).quantize(Decimal("0.01"))
    db.add(
        InvoiceLine(
            invoice_id=invoice.id,
            position=1,
            kind="OTHER",
            description="Imported total",
            unit="st",
            quantity=Decimal("1.00"),
            unit_price_ex_vat=work_sum,
            vat_rate_pct=vat_rate,
            source_type="MANUAL",
        )
    )
    recalculate_invoice_totals(db, invoice.id, user_id=request.session.get("user_email"))
    db.commit()

    return RedirectResponse(
        url=f"/projects/{project.id}/invoices/", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/{invoice_id}", response_class=HTMLResponse)
async def invoice_document(
    project_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    company_profile = get_or_create_company_profile(db)
    if invoice.status == "issued":
        terms_title = invoice.invoice_terms_snapshot_title or ""
        terms_body = invoice.invoice_terms_snapshot_body or ""
    else:
        terms_template = resolve_terms_template(
            db,
            profile=company_profile,
            client=invoice.project.client,
            doc_type=DOC_TYPE_INVOICE,
            lang=lang,
        )
        terms_title = terms_template.title
        terms_body = terms_template.body_text
    context = template_context(request, lang)
    context.update({"project": invoice.project, "invoice": invoice, "company_profile": company_profile, "terms_title": terms_title, "terms_body": terms_body})
    return templates.TemplateResponse(request, "invoices/document.html", context)


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
    company_profile = get_or_create_company_profile(db)

    context = template_context(request, lang)
    can_edit = request.session.get("user_role") in {ADMIN_ROLE, OPERATOR_ROLE} and invoice.status != "issued"
    context.update(
        {
            "project": project,
            "invoice": invoice,
            "statuses": INVOICE_STATUSES,
            "defaults": None,
            "action_url": f"/projects/{project.id}/invoices/{invoice.id}/edit",
            "company_profile": company_profile,
            "can_edit": can_edit,
            "merge_strategies": [MERGE_REPLACE_ALL, MERGE_APPEND, MERGE_UPSERT_BY_SOURCE],
        }
    )
    return templates.TemplateResponse(request, "invoices/form.html", context)


@router.post("/{invoice_id}/edit")
async def update_invoice(
    project_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    _ensure_editable(invoice)
    form = await request.form()

    invoice.issue_date = _parse_date(form.get("issue_date")) or invoice.issue_date
    invoice.due_date = _parse_date(form.get("due_date"))
    invoice.paid_date = _parse_date(form.get("paid_date"))
    requested_status = form.get("status")
    if requested_status in INVOICE_STATUSES and requested_status != "issued":
        invoice.status = requested_status
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
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    db.delete(invoice)
    db.commit()

    return RedirectResponse(
        url=f"/projects/{project_id}/invoices/", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/create-from-project")
async def create_invoice_from_project(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    project = _get_project(db, project_id)
    form = await request.form()

    include_labor = str(form.get("include_labor") or "true").lower() == "true"
    include_materials = str(form.get("include_materials") or "false").lower() == "true"
    merge_strategy = (form.get("merge_strategy") or MERGE_REPLACE_ALL).upper()
    note = (form.get("note") or "").strip() or None

    idempotency_key = request.headers.get("Idempotency-Key") or str(uuid.uuid4())

    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.lines))
        .filter(Invoice.source_project_id == project.id, Invoice.status == "draft")
        .order_by(Invoice.id.desc())
        .first()
    )

    if invoice is None:
        invoice = Invoice(
            project_id=project.id,
            source_project_id=project.id,
            invoice_number=None,
            issue_date=date.today(),
            due_date=None,
            paid_date=None,
            status="draft",
            work_sum_without_moms=Decimal("0.00"),
            moms_amount=Decimal("0.00"),
            rot_amount=Decimal("0.00"),
            client_pays_total=Decimal("0.00"),
            comment=note,
        )
        db.add(invoice)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            invoice = (
                db.query(Invoice)
                .options(selectinload(Invoice.lines))
                .filter(Invoice.source_project_id == project.id, Invoice.status == "draft")
                .order_by(Invoice.id.desc())
                .first()
            )
            if invoice is None:
                raise HTTPException(status_code=409, detail="Unable to create draft invoice. Retry with same request.")
    elif note and not invoice.comment:
        invoice.comment = note

    if invoice.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft invoices can be generated from project")

    generate_invoice_lines_from_project(
        db,
        project_id=project.id,
        invoice_id=invoice.id,
        include_labor=include_labor,
        include_materials=include_materials,
        merge_strategy=merge_strategy,
        user_id=request.session.get("user_email"),
    )

    db.add(
        AuditEvent(
            event_type="invoice_created_from_project",
            user_id=request.session.get("user_email"),
            entity_type="project",
            entity_id=project.id,
            details=f"invoice_id={invoice.id};idempotency_key={idempotency_key}",
        )
    )
    db.commit()

    logger.info(
        "invoice_create_from_project project_id=%s invoice_id=%s include_labor=%s include_materials=%s merge_strategy=%s lines=%s request_id=%s",
        project.id,
        invoice.id,
        include_labor,
        include_materials,
        merge_strategy,
        len(invoice.lines),
        request.state.request_id,
    )

    return RedirectResponse(
        url=f"/projects/{project.id}/invoices/{invoice.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{invoice_id}/generate-lines")
async def generate_lines(
    project_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    _ensure_editable(invoice)
    form = await request.form()
    include_labor = str(form.get("include_labor") or "true").lower() == "true"
    include_materials = str(form.get("include_materials") or "false").lower() == "true"
    merge_strategy = (form.get("merge_strategy") or MERGE_REPLACE_ALL).upper()
    generate_invoice_lines_from_project(
        db,
        project_id=project_id,
        invoice_id=invoice_id,
        include_labor=include_labor,
        include_materials=include_materials,
        merge_strategy=merge_strategy,
        user_id=request.session.get("user_email"),
    )
    db.commit()
    return RedirectResponse(
        url=f"/projects/{project_id}/invoices/{invoice_id}/edit",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{invoice_id}/lines/add")
async def add_invoice_line(
    project_id: int,
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    _ensure_editable(invoice)
    pos = (max((line.position for line in invoice.lines), default=0)) + 1
    line = InvoiceLine(
        invoice_id=invoice.id,
        position=pos,
        kind="OTHER",
        description="Manual line",
        unit="st",
        quantity=Decimal("1.00"),
        unit_price_ex_vat=Decimal("0.00"),
        vat_rate_pct=Decimal("25.00"),
        source_type="MANUAL",
    )
    db.add(line)
    db.flush()
    db.add(AuditEvent(event_type="invoice_line_added", user_id=request.session.get("user_email"), entity_type="invoice", entity_id=invoice.id, details=f"line_id={line.id}"))
    recalculate_invoice_totals(db, invoice.id, user_id=request.session.get("user_email"))
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/invoices/{invoice_id}/edit", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{invoice_id}/lines/{line_id}/delete")
async def delete_invoice_line(
    project_id: int,
    invoice_id: int,
    line_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    _ensure_editable(invoice)
    line = db.query(InvoiceLine).filter(InvoiceLine.id == line_id, InvoiceLine.invoice_id == invoice_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")
    db.add(AuditEvent(event_type="invoice_line_deleted", user_id=request.session.get("user_email"), entity_type="invoice", entity_id=invoice.id, details=f"line_id={line.id}"))
    db.delete(line)
    db.flush()
    for idx, candidate in enumerate(sorted(invoice.lines, key=lambda ln: ln.position), start=1):
        candidate.position = idx
        db.add(candidate)
    recalculate_invoice_totals(db, invoice.id, user_id=request.session.get("user_email"))
    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/invoices/{invoice_id}/edit", status_code=status.HTTP_303_SEE_OTHER)


@router.patch("/{invoice_id}/lines/{line_id}")
async def update_invoice_line(
    project_id: int,
    invoice_id: int,
    line_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role(ADMIN_ROLE, OPERATOR_ROLE)),
):
    invoice = _get_invoice(db, project_id, invoice_id)
    _ensure_editable(invoice)
    line = db.query(InvoiceLine).filter(InvoiceLine.id == line_id, InvoiceLine.invoice_id == invoice_id).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")
    payload = await request.json()
    line.description = str(payload.get("description", line.description))
    line.unit = payload.get("unit", line.unit)
    line.quantity = Decimal(str(payload.get("quantity", line.quantity or 0)))
    line.unit_price_ex_vat = Decimal(str(payload.get("unit_price_ex_vat", line.unit_price_ex_vat or 0)))
    line.vat_rate_pct = Decimal(str(payload.get("vat_rate_pct", line.vat_rate_pct or 25)))
    db.add(AuditEvent(event_type="invoice_line_updated", user_id=request.session.get("user_email"), entity_type="invoice", entity_id=invoice.id, details=f"line_id={line.id}"))
    recalculate_invoice_totals(db, invoice.id, user_id=request.session.get("user_email"))
    db.commit()
    return JSONResponse({"ok": True, "invoice_total": str(invoice.total_inc_vat)})
