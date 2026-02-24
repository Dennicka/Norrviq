import logging
from pathlib import Path
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload

from app.dependencies import add_flash_message, get_current_lang, get_db
from app.audit import log_event
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.models.project import ProjectWorkItem
from app.observability import REQUEST_ID_HEADER
from app.security import require_role
from app.services.estimates import calculate_project_totals, recalculate_project_work_items
from app.services.offer_commercial import compute_offer_commercial, deserialize_offer_commercial
from app.services.invoice_commercial import compute_invoice_commercial
from app.services.commercial_snapshot import DOC_TYPE_INVOICE as SNAP_INVOICE, DOC_TYPE_OFFER as SNAP_OFFER, read_commercial_snapshot
from app.services.document_numbering import (
    CompletenessViolationError,
    FloorPolicyViolationError,
    NumberingConflictError,
    finalize_invoice,
    finalize_offer,
)
from app.services.pdf_export import render_pdf_from_html
from app.services.completeness import compute_completeness
from app.services.quality import evaluate_project_quality
from app.services.terms_templates import DOC_TYPE_INVOICE, DOC_TYPE_OFFER, resolve_terms_template
from app.dependencies import template_context, templates

router = APIRouter(tags=["document-finalize"])
logger = logging.getLogger("app.pdf")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_STYLESHEET = PROJECT_ROOT / "app" / "static" / "css" / "pdf_document.css"


def _quality_gate_response(request: Request, *, project_id: int, issues: list[dict]):
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(status_code=409, content={"detail": "Нельзя выпустить документ, исправьте критические проблемы", "issues": issues})
    add_flash_message(request, "Нельзя выпустить документ, исправь критические проблемы качества данных", "error")
    return RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)


def _completeness_gate_response(request: Request, *, project_id: int, exc: CompletenessViolationError):
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "score": exc.score,
                "missing": exc.missing,
                "project_url": f"/projects/{project_id}",
                "rooms_url": f"/projects/{project_id}/rooms/",
                "pricing_url": f"/projects/{project_id}/pricing",
            },
        )
    add_flash_message(request, f"{exc}. Перейдите в Project/Rooms/Pricing.", "error")
    return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)


def _completeness_mode_gate_response(request: Request, *, project_id: int, score: int, reasons: list[dict]):
    detail = "Нельзя выпустить документ: недостаточно данных"
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            status_code=409,
            content={
                "detail": detail,
                "score": score,
                "reasons": reasons,
                "project_url": f"/projects/{project_id}",
                "rooms_url": f"/projects/{project_id}/rooms/",
                "pricing_url": f"/projects/{project_id}/pricing",
            },
        )
    add_flash_message(request, detail, "error")
    return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)


def _check_fixed_mode_completeness(db: Session, *, project_id: int, lang: str) -> tuple[bool, int, list[dict]]:
    project = db.get(Project, project_id)
    if not project:
        return True, 100, []
    mode = project.pricing.mode if project.pricing else "HOURLY"
    if mode != "FIXED_TOTAL":
        return True, 100, []

    segment = project.client.client_segment if project.client and project.client.client_segment else "B2C"
    report = compute_completeness(db, project_id, mode=mode, segment=segment, lang=lang)
    policy = get_or_create_pricing_policy(db)
    if policy.warn_only_mode:
        return True, report.score, []
    min_score = int(policy.min_completeness_score_for_fixed or 70)
    blocked = (not report.can_issue_mode) or (report.score < min_score)
    reasons = [
        {"check_key": item.check_key, "severity": item.severity, "message": item.message, "hint_link": item.hint_link}
        for item in report.missing[:3]
    ]
    return (not blocked), report.score, reasons


def _filename(*, kind: str, number: str | None, fallback: str) -> str:
    safe_number = (number or fallback).replace(" ", "_").replace("/", "-")
    return f'Trenor_{kind}_{safe_number}.pdf'


def _audit_pdf_download(db: Session, *, request: Request, event_type: str, entity_type: str, entity_id: int, status_value: str) -> None:
    request_id = getattr(request.state, "request_id", None)
    log_event(
        db,
        request,
        event_type,
        entity_type=entity_type.upper(),
        entity_id=entity_id,
        metadata={"status": status_value, "request_id": request_id},
    )
    db.commit()
    logger.info(
        "event=%s doc_id=%s status=%s request_id=%s",
        event_type,
        entity_id,
        status_value,
        request_id,
    )


@router.get("/offers/{offer_id}/pdf")
async def offer_pdf(
    offer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator", "viewer")),
):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.client),
            selectinload(Project.work_items).selectinload(ProjectWorkItem.work_type),
        )
        .filter(Project.id == offer_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Offer not found")

    recalculate_project_work_items(db, project)
    calculate_project_totals(db, project)

    if project.offer_status == "issued":
        snap = read_commercial_snapshot(db, doc_type=SNAP_OFFER, doc_id=project.id)
        commercial = None
        if snap:
            commercial = {
                "mode": snap["mode"],
                "units": snap["units"],
                "rate": snap["rates"],
                "line_items": snap["line_items"],
                "price_ex_vat": Decimal(str(snap["totals"].get("price_ex_vat") or 0)),
                "vat_amount": Decimal(str(snap["totals"].get("vat_amount") or 0)),
                "price_inc_vat": Decimal(str(snap["totals"].get("price_inc_vat") or 0)),
                "warnings": [],
                "math_breakdown": {},
                "sections": [{"id": "default", "title": "", "order": 10, "lines": snap["line_items"]}],
                "summary": {
                    "subtotal_ex_vat": Decimal(str(snap["totals"].get("price_ex_vat") or 0)),
                    "vat_amount": Decimal(str(snap["totals"].get("vat_amount") or 0)),
                    "total_inc_vat": Decimal(str(snap["totals"].get("price_inc_vat") or 0)),
                },
                "metadata": {},
            }
        if commercial is None:
            commercial = deserialize_offer_commercial(project.offer_commercial_snapshot)
    else:
        commercial = None
    if commercial is None:
        computed = compute_offer_commercial(db, project.id, lang=lang)
        commercial = {
            "mode": computed.mode,
            "units": computed.units,
            "line_items": computed.line_items,
            "price_ex_vat": computed.price_ex_vat,
            "vat_amount": computed.vat_amount,
            "price_inc_vat": computed.price_inc_vat,
            "warnings": computed.warnings,
            "math_breakdown": computed.math_breakdown,
            "sections": computed.sections,
            "summary": computed.summary,
            "metadata": computed.metadata,
        }

    profile = get_or_create_company_profile(db)
    if project.offer_status == "issued":
        terms_title = project.offer_terms_snapshot_title or ""
        terms_body = project.offer_terms_snapshot_body or ""
    else:
        template = resolve_terms_template(db, profile=profile, client=project.client, doc_type=DOC_TYPE_OFFER, lang=lang)
        terms_title = template.title
        terms_body = template.body_text

    context = template_context(request, lang)
    context.update(
        {
            "project": project,
            "client": project.client,
            "work_items": commercial["line_items"],
            "commercial": commercial,
            "company_profile": profile,
            "offer_number": project.offer_number,
            "offer_status": project.offer_status,
            "offer_date": project.created_at.date() if project.created_at else date.today(),
            "terms_title": terms_title,
            "terms_body": terms_body,
            "is_draft": project.offer_status != "issued",
        }
    )
    html = templates.get_template("pdf/offer_pdf.html").render(context)
    try:
        pdf_bytes = render_pdf_from_html(html=html, base_url=PROJECT_ROOT, stylesheet_path=PDF_STYLESHEET)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit_pdf_download(
        db,
        request=request,
        event_type="offer_pdf_downloaded",
        entity_type="project",
        entity_id=project.id,
        status_value=project.offer_status,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_filename(kind="Offer", number=project.offer_number, fallback="DRAFT")}"',
            REQUEST_ID_HEADER: getattr(request.state, "request_id", ""),
        },
    )


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator", "viewer")),
):
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.project).selectinload(Project.client), selectinload(Invoice.lines))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    profile = get_or_create_company_profile(db)
    if invoice.status == "issued":
        terms_title = invoice.invoice_terms_snapshot_title or ""
        terms_body = invoice.invoice_terms_snapshot_body or ""
    else:
        template = resolve_terms_template(db, profile=profile, client=invoice.project.client, doc_type=DOC_TYPE_INVOICE, lang=lang)
        terms_title = template.title
        terms_body = template.body_text

    commercial = compute_invoice_commercial(db, invoice.project_id, invoice.id, lang=lang)
    if invoice.status == "issued":
        snap = read_commercial_snapshot(db, doc_type=SNAP_INVOICE, doc_id=invoice.id)
        if snap:
            commercial.mode = snap["mode"]
            commercial.units = snap["units"]
            commercial.rate = snap["rates"]
            commercial.price_ex_vat = Decimal(str(snap["totals"].get("price_ex_vat") or invoice.subtotal_ex_vat))
            commercial.vat_amount = Decimal(str(snap["totals"].get("vat_amount") or invoice.vat_total))
            commercial.price_inc_vat = Decimal(str(snap["totals"].get("price_inc_vat") or invoice.total_inc_vat))

    context = template_context(request, lang)
    context.update(
        {
            "invoice": invoice,
            "commercial": commercial,
            "company_profile": profile,
            "terms_title": terms_title,
            "terms_body": terms_body,
            "is_draft": invoice.status != "issued",
        }
    )
    html = templates.get_template("pdf/invoice_pdf.html").render(context)
    try:
        pdf_bytes = render_pdf_from_html(html=html, base_url=PROJECT_ROOT, stylesheet_path=PDF_STYLESHEET)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit_pdf_download(
        db,
        request=request,
        event_type="invoice_pdf_downloaded",
        entity_type="invoice",
        entity_id=invoice.id,
        status_value=invoice.status,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_filename(kind="Invoice", number=invoice.invoice_number, fallback="DRAFT")}"',
            REQUEST_ID_HEADER: getattr(request.state, "request_id", ""),
        },
    )




@router.get("/commercial-snapshots/{doc_type}/{doc_id}")
async def view_commercial_snapshot(
    doc_type: str,
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_role("admin", "operator")),
):
    snap = read_commercial_snapshot(db, doc_type=doc_type.upper(), doc_id=doc_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Commercial snapshot not found")
    return JSONResponse(content={
        "doc_type": doc_type.upper(),
        "doc_id": doc_id,
        "snapshot": snap,
        "request_id": getattr(request.state, "request_id", ""),
    })


@router.post("/offers/{project_id}/finalize")
async def finalize_offer_action(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    profile = get_or_create_company_profile(db)
    user_id = request.session.get("user_email") if hasattr(request, "session") else None
    form = await request.form()
    terms_lang = form.get("terms_lang")

    can_issue, score, reasons = _check_fixed_mode_completeness(db, project_id=project_id, lang=_lang)
    if not can_issue:
        return _completeness_mode_gate_response(request, project_id=project_id, score=score, reasons=reasons)

    quality_report = evaluate_project_quality(db, project_id, lang=_lang)
    if quality_report.blocks_count > 0:
        issues = [{"field": i.field, "message": i.message, "entity": i.entity, "entity_id": i.entity_id} for i in quality_report.issues if i.severity == "BLOCK"]
        log_event(db, request, "issue_blocked_document_issue", entity_type="PROJECT", entity_id=project_id, severity="WARN", metadata={"issues": issues, "user_id": user_id})
        db.commit()
        return _quality_gate_response(request, project_id=project_id, issues=issues)
    if quality_report.warnings_count > 0:
        add_flash_message(request, "Есть предупреждения качества данных", "warning")
    try:
        finalize_offer(db, project_id=project_id, user_id=user_id, profile=profile, lang=terms_lang)
        add_flash_message(request, "Offer finalized", "success")
    except NumberingConflictError:
        req_id = getattr(request.state, "request_id", "-")
        add_flash_message(request, f"Номер уже выдан, обновите страницу (request_id={req_id})", "error")
    except CompletenessViolationError as exc:
        return _completeness_gate_response(request, project_id=project_id, exc=exc)
    except FloorPolicyViolationError as exc:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=409, content={"detail": str(exc), "reasons": exc.reasons, "pricing_url": f"/projects/{project_id}/pricing"})
        add_flash_message(request, f"{exc}. Перейдите в Pricing.", "error")
        return RedirectResponse(url=f"/projects/{project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as exc:
        if "Offer totals mismatch pricing scenario" in str(exc):
            req_id = getattr(request.state, "request_id", "")
            payload = {"detail": "Offer totals mismatch pricing scenario", "request_id": req_id}
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(status_code=409, content=payload)
            add_flash_message(request, f"{payload['detail']} (request_id={req_id})", "error")
            return RedirectResponse(url=f"/projects/{project_id}/offer", status_code=status.HTTP_303_SEE_OTHER)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RedirectResponse(url=f"/projects/{project_id}/offer", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/invoices/{invoice_id}/finalize")
async def finalize_invoice_action(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    profile = get_or_create_company_profile(db)
    user_id = request.session.get("user_email") if hasattr(request, "session") else None
    form = await request.form()
    terms_lang = form.get("terms_lang")
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    can_issue, score, reasons = _check_fixed_mode_completeness(db, project_id=invoice.project_id, lang=_lang)
    if not can_issue:
        return _completeness_mode_gate_response(request, project_id=invoice.project_id, score=score, reasons=reasons)

    quality_report = evaluate_project_quality(db, invoice.project_id, lang=_lang)
    if quality_report.blocks_count > 0:
        issues = [{"field": i.field, "message": i.message, "entity": i.entity, "entity_id": i.entity_id} for i in quality_report.issues if i.severity == "BLOCK"]
        log_event(db, request, "issue_blocked_document_issue", entity_type="INVOICE", entity_id=invoice_id, severity="WARN", metadata={"issues": issues, "user_id": user_id})
        db.commit()
        return _quality_gate_response(request, project_id=invoice.project_id, issues=issues)
    if quality_report.warnings_count > 0:
        add_flash_message(request, "Есть предупреждения качества данных", "warning")

    try:
        finalize_invoice(db, invoice_id=invoice_id, user_id=user_id, profile=profile, lang=terms_lang)
        add_flash_message(request, "Invoice finalized", "success")
    except NumberingConflictError:
        req_id = getattr(request.state, "request_id", "-")
        add_flash_message(request, f"Номер уже выдан, обновите страницу (request_id={req_id})", "error")
    except CompletenessViolationError as exc:
        return _completeness_gate_response(request, project_id=invoice.project_id, exc=exc)
    except FloorPolicyViolationError as exc:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=409, content={"detail": str(exc), "reasons": exc.reasons, "pricing_url": f"/projects/{invoice.project_id}/pricing"})
        add_flash_message(request, f"{exc}. Перейдите в Pricing.", "error")
        return RedirectResponse(url=f"/projects/{invoice.project_id}/pricing", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as exc:
        if "Invoice totals mismatch pricing scenario" in str(exc) or "Enable include_materials in pricing or remove material lines" in str(exc):
            req_id = getattr(request.state, "request_id", "")
            payload = {"detail": str(exc), "request_id": req_id}
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(status_code=409, content=payload)
            add_flash_message(request, f"{payload['detail']} (request_id={req_id})", "error")
            return RedirectResponse(url=f"/projects/{invoice.project_id}/invoices/{invoice_id}", status_code=status.HTTP_303_SEE_OTHER)

    response = RedirectResponse(url=f"/projects/{invoice.project_id}/invoices/{invoice_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.headers[REQUEST_ID_HEADER] = getattr(request.state, "request_id", "")
    return response
