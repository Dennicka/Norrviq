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
from app.services.pdf_renderer import invoice_pdf_capability, render_invoice_pdf
from app.services.completeness import compute_completeness
from app.services.quality import evaluate_project_quality
from app.services.terms_templates import DOC_TYPE_OFFER, resolve_terms_template
from app.services.invoice_documents import invoice_render_lang, normalize_document_lang, resolve_invoice_terms, format_doc_date, format_doc_money
from app.services.correctness_lock import validate_offer_invariants, validate_invoice_invariants
from app.dependencies import template_context, templates
from app.i18n import make_t

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


def _build_offer_render_context(*, request: Request, db: Session, project: Project, render_lang: str) -> dict:
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
        computed = compute_offer_commercial(db, project.id, lang=render_lang)
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
        template = resolve_terms_template(db, profile=profile, client=project.client, doc_type=DOC_TYPE_OFFER, lang=render_lang)
        terms_title = template.title
        terms_body = template.body_text

    context = template_context(request, render_lang)
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
    return context


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

    render_lang = normalize_document_lang(lang, fallback=normalize_document_lang(project.offer_document_lang))
    context = _build_offer_render_context(request=request, db=db, project=project, render_lang=render_lang)
    html = templates.get_template("pdf/offer_pdf.html").render(context)
    try:
        pdf_bytes = render_pdf_from_html(html=html, base_url=PROJECT_ROOT, stylesheet_path=PDF_STYLESHEET)
    except RuntimeError:
        context["show_pdf_fallback_hint"] = True
        add_flash_message(request, make_t(render_lang)("invoice.pdf_fallback_mode"), "warning")
        return templates.TemplateResponse(request, "pdf/offer_pdf.html", context)
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


@router.get("/offers/{offer_id}/print")
async def offer_print_view(
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

    render_lang = normalize_document_lang(lang, fallback=normalize_document_lang(project.offer_document_lang))
    context = _build_offer_render_context(request=request, db=db, project=project, render_lang=render_lang)
    context["show_print_toolbar"] = True
    return templates.TemplateResponse(request, "pdf/offer_pdf.html", context)


@router.get("/offers/{offer_id}")
async def offer_document_redirect(offer_id: int, lang: str = Depends(get_current_lang)):
    return RedirectResponse(url=f"/projects/{offer_id}/offer?lang={normalize_document_lang(lang)}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/invoices/{invoice_id}")
async def invoice_document_redirect(
    invoice_id: int,
    db: Session = Depends(get_db),
    lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator", "viewer")),
):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return RedirectResponse(url=f"/projects/{invoice.project_id}/invoices/{invoice_id}?lang={normalize_document_lang(lang)}", status_code=status.HTTP_303_SEE_OTHER)


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
    render_lang = invoice_render_lang(invoice, lang)
    terms_resolution = resolve_invoice_terms(db, profile=profile, invoice=invoice, requested_lang=render_lang)

    commercial = compute_invoice_commercial(db, invoice.project_id, invoice.id, lang=render_lang)
    if invoice.status == "issued":
        snap = read_commercial_snapshot(db, doc_type=SNAP_INVOICE, doc_id=invoice.id)
        if snap:
            commercial.mode = snap["mode"]
            commercial.units = snap["units"]
            commercial.rate = snap["rates"]
            commercial.price_ex_vat = Decimal(str(snap["totals"].get("price_ex_vat") or invoice.subtotal_ex_vat))
            commercial.vat_amount = Decimal(str(snap["totals"].get("vat_amount") or invoice.vat_total))
            commercial.price_inc_vat = Decimal(str(snap["totals"].get("price_inc_vat") or invoice.total_inc_vat))

    context = template_context(request, render_lang)
    context.update(
        {
            "invoice": invoice,
            "commercial": commercial,
            "company_profile": profile,
            "terms_title": terms_resolution.title,
            "terms_body": terms_resolution.body,
            "terms_fallback": terms_resolution.used_fallback,
            "terms_requested_lang": terms_resolution.requested_lang,
            "terms_resolved_lang": terms_resolution.resolved_lang,
            "document_lang": render_lang,
            "format_doc_date": format_doc_date,
            "format_doc_money": format_doc_money,
            "is_draft": invoice.status != "issued",
        }
    )
    html = templates.get_template("pdf/invoice_pdf.html").render(context)
    pdf_bytes = render_invoice_pdf(
        invoice.id,
        render_lang,
        html=html,
        base_url=PROJECT_ROOT,
        stylesheet_path=PDF_STYLESHEET,
        render_pdf=render_pdf_from_html,
    )
    if pdf_bytes is None:
        add_flash_message(request, make_t(render_lang)("invoice.pdf_fallback_mode"), "warning")
        context["pdf_capability"] = invoice_pdf_capability()
        return templates.TemplateResponse(request, "invoices/print.html", context)
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


@router.get("/invoices/{invoice_id}/print")
async def invoice_print_view(
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
    render_lang = invoice_render_lang(invoice, lang)
    terms_resolution = resolve_invoice_terms(db, profile=profile, invoice=invoice, requested_lang=render_lang)

    commercial = compute_invoice_commercial(db, invoice.project_id, invoice.id, lang=render_lang)
    if invoice.status == "issued":
        snap = read_commercial_snapshot(db, doc_type=SNAP_INVOICE, doc_id=invoice.id)
        if snap:
            commercial.mode = snap["mode"]
            commercial.units = snap["units"]
            commercial.rate = snap["rates"]
            commercial.price_ex_vat = Decimal(str(snap["totals"].get("price_ex_vat") or invoice.subtotal_ex_vat))
            commercial.vat_amount = Decimal(str(snap["totals"].get("vat_amount") or invoice.vat_total))
            commercial.price_inc_vat = Decimal(str(snap["totals"].get("price_inc_vat") or invoice.total_inc_vat))

    context = template_context(request, render_lang)
    context.update(
        {
            "invoice": invoice,
            "commercial": commercial,
            "company_profile": profile,
            "terms_title": terms_resolution.title,
            "terms_body": terms_resolution.body,
            "terms_fallback": terms_resolution.used_fallback,
            "terms_requested_lang": terms_resolution.requested_lang,
            "terms_resolved_lang": terms_resolution.resolved_lang,
            "document_lang": render_lang,
            "format_doc_date": format_doc_date,
            "format_doc_money": format_doc_money,
            "is_draft": invoice.status != "issued",
            "pdf_capability": invoice_pdf_capability(),
        }
    )
    return templates.TemplateResponse(request, "invoices/print.html", context)




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
        add_flash_message(request, make_t(_lang)("documents.quality_warnings"), "warning")
    try:
        project = finalize_offer(db, project_id=project_id, user_id=user_id, profile=profile, lang=terms_lang)
        lock = validate_offer_invariants(db, project)
        if not lock.ok:
            logger.error("correctness_lock_failed action=finalize_offer route=%s project_id=%s request_id=%s user_email=%s errors=%s", request.url.path, project_id, getattr(request.state, "request_id", None), user_id, lock.errors)
            add_flash_message(request, make_t(_lang)("correctness.lock_failed"), "error")
            return RedirectResponse(url=f"/projects/{project_id}/offer", status_code=status.HTTP_303_SEE_OTHER)
        add_flash_message(request, make_t(_lang)("documents.offer_finalized"), "success")
    except NumberingConflictError:
        req_id = getattr(request.state, "request_id", "-")
        add_flash_message(request, make_t(_lang)("documents.number_already_issued").format(request_id=req_id), "error")
    except CompletenessViolationError as exc:
        return _completeness_gate_response(request, project_id=project_id, exc=exc)
    except FloorPolicyViolationError as exc:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=409, content={"detail": str(exc), "reasons": exc.reasons, "pricing_url": f"/projects/{project_id}/pricing"})
        add_flash_message(request, make_t(_lang)("documents.go_to_pricing").format(message=exc), "error")
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


@router.post("/offers/{project_id}/issue")
async def issue_offer_action(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    return await finalize_offer_action(project_id=project_id, request=request, db=db, _lang=_lang, _role=_role)


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
        add_flash_message(request, make_t(_lang)("documents.quality_warnings"), "warning")

    try:
        invoice = finalize_invoice(db, invoice_id=invoice_id, user_id=user_id, profile=profile, lang=terms_lang)
        lock = validate_invoice_invariants(db, invoice)
        if not lock.ok:
            logger.error("correctness_lock_failed action=finalize_invoice route=%s project_id=%s invoice_id=%s request_id=%s user_email=%s errors=%s", request.url.path, invoice.project_id, invoice_id, getattr(request.state, "request_id", None), user_id, lock.errors)
            add_flash_message(request, make_t(_lang)("correctness.lock_failed"), "error")
            return RedirectResponse(url=f"/projects/{invoice.project_id}/invoices/{invoice_id}", status_code=status.HTTP_303_SEE_OTHER)
        add_flash_message(request, make_t(_lang)("documents.invoice_finalized"), "success")
    except NumberingConflictError:
        req_id = getattr(request.state, "request_id", "-")
        add_flash_message(request, make_t(_lang)("documents.number_already_issued").format(request_id=req_id), "error")
    except CompletenessViolationError as exc:
        return _completeness_gate_response(request, project_id=invoice.project_id, exc=exc)
    except FloorPolicyViolationError as exc:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=409, content={"detail": str(exc), "reasons": exc.reasons, "pricing_url": f"/projects/{invoice.project_id}/pricing"})
        add_flash_message(request, make_t(_lang)("documents.go_to_pricing").format(message=exc), "error")
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


@router.post("/invoices/{invoice_id}/issue")
async def issue_invoice_action(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _lang: str = Depends(get_current_lang),
    _role: str = Depends(require_role("admin", "operator")),
):
    return await finalize_invoice_action(invoice_id=invoice_id, request=request, db=db, _lang=_lang, _role=_role)
