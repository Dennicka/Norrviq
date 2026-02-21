from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import add_flash_message, get_current_lang, get_db
from app.models.company_profile import get_or_create_company_profile
from app.models.invoice import Invoice
from app.observability import REQUEST_ID_HEADER
from app.security import require_role
from app.services.document_numbering import NumberingConflictError, finalize_invoice, finalize_offer

router = APIRouter(tags=["document-finalize"])


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
    try:
        finalize_offer(db, project_id=project_id, user_id=user_id, profile=profile, lang=terms_lang)
        add_flash_message(request, "Offer finalized", "success")
    except NumberingConflictError:
        req_id = getattr(request.state, "request_id", "-")
        add_flash_message(request, f"Номер уже выдан, обновите страницу (request_id={req_id})", "error")
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

    try:
        finalize_invoice(db, invoice_id=invoice_id, user_id=user_id, profile=profile, lang=terms_lang)
        add_flash_message(request, "Invoice finalized", "success")
    except NumberingConflictError:
        req_id = getattr(request.state, "request_id", "-")
        add_flash_message(request, f"Номер уже выдан, обновите страницу (request_id={req_id})", "error")

    response = RedirectResponse(
        url=f"/projects/{invoice.project_id}/invoices/{invoice_id}", status_code=status.HTTP_303_SEE_OTHER
    )
    response.headers[REQUEST_ID_HEADER] = getattr(request.state, "request_id", "")
    return response
