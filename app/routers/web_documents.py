from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db
from app.models.audit_event import AuditEvent
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.observability import REQUEST_ID_HEADER
from app.security import require_role
from app.services.document_numbering import (
    CompletenessViolationError,
    FloorPolicyViolationError,
    NumberingConflictError,
    finalize_invoice,
    finalize_offer,
)
from app.services.completeness import compute_completeness
from app.services.quality import evaluate_project_quality

router = APIRouter(tags=["document-finalize"])


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
        db.add(AuditEvent(event_type="issue_blocked_document_issue", user_id=user_id, entity_type="project", entity_id=project_id, details=str(issues)))
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
        db.add(AuditEvent(event_type="issue_blocked_document_issue", user_id=user_id, entity_type="invoice", entity_id=invoice_id, details=str(issues)))
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

    response = RedirectResponse(url=f"/projects/{invoice.project_id}/invoices/{invoice_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.headers[REQUEST_ID_HEADER] = getattr(request.state, "request_id", "")
    return response
