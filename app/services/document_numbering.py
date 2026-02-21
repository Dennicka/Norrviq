import json
import logging
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.company_profile import CompanyProfile
from app.models.document_sequence import DocumentSequence
from app.models.invoice import Invoice
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.services.pricing import compute_pricing_scenarios, evaluate_floor
from app.services.terms_templates import DOC_TYPE_INVOICE, DOC_TYPE_OFFER, resolve_terms_template

logger = logging.getLogger("uvicorn.error")

DOC_TYPE_OFFER_NUMBERING = "offer"
DOC_TYPE_INVOICE_NUMBERING = "invoice"
STATUS_DRAFT = "draft"
STATUS_ISSUED = "issued"


class NumberingConflictError(RuntimeError):
    pass


class FloorPolicyViolationError(RuntimeError):
    def __init__(self, *, doc_type: str, doc_id: int, project_id: int, reasons: list[dict]):
        super().__init__("Нельзя выпустить документ: ниже минимальной маржи")
        self.doc_type = doc_type
        self.doc_id = doc_id
        self.project_id = project_id
        self.reasons = reasons


def _check_floor_policy_for_project(db: Session, *, project_id: int, user_id: str | None, doc_type: str, doc_id: int) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found")

    policy = get_or_create_pricing_policy(db)
    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    selected_mode = project.pricing.mode if project.pricing else "HOURLY"
    selected = next((scenario for scenario in scenarios if scenario.mode == selected_mode), None)
    if selected is None:
        return
    floor = evaluate_floor(baseline, selected, policy)
    if not floor.is_below_floor:
        return

    reason_codes = [item.code for item in floor.reasons]
    reason_payload = [{"code": item.code, "text": item.text} for item in floor.reasons]

    event_type = "floor_warning_issue" if policy.warn_only_mode else "floor_blocked_issue"
    _create_audit_event(
        db,
        event_type=event_type,
        user_id=user_id,
        entity_type=doc_type,
        entity_id=doc_id,
        details={"doc_type": doc_type, "doc_id": doc_id, "project_id": project_id, "reasons": reason_codes},
    )
    logger.warning("event=%s doc_type=%s doc_id=%s project_id=%s reason_codes=%s", event_type, doc_type, doc_id, project_id, ",".join(reason_codes))

    if policy.warn_only_mode:
        return
    if policy.block_issue_below_floor:
        raise FloorPolicyViolationError(doc_type=doc_type, doc_id=doc_id, project_id=project_id, reasons=reason_payload)


def format_document_number(prefix: str, year: int, sequence: int, padding: int) -> str:
    effective_padding = max(int(padding or 4), 1)
    return f"{prefix}{year}-{sequence:0{effective_padding}d}"


def _lock_for_issuance(db: Session) -> None:
    if db.bind and db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _next_sequence(db: Session, doc_type: str, year: int) -> int:
    query = db.query(DocumentSequence).filter(
        DocumentSequence.doc_type == doc_type,
        DocumentSequence.year == year,
    )
    if db.bind and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()

    seq_row = query.first()
    if seq_row is None:
        seq_row = DocumentSequence(doc_type=doc_type, year=year, next_number=1)
        db.add(seq_row)
        db.flush()

    seq = seq_row.next_number
    seq_row.next_number = seq + 1
    db.add(seq_row)
    return seq


def _create_audit_event(db: Session, *, event_type: str, user_id: str | None, entity_type: str, entity_id: int, details: dict) -> None:
    db.add(
        AuditEvent(
            event_type=event_type,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(details, ensure_ascii=False),
        )
    )


def finalize_offer(db: Session, project_id: int, user_id: str | None, profile: CompanyProfile, lang: str | None = None) -> Project:
    try:
        _lock_for_issuance(db)
        project = db.get(Project, project_id)
        if not project:
            raise ValueError("Project not found")

        if project.offer_status == STATUS_ISSUED and project.offer_number:
            db.commit()
            return project

        _check_floor_policy_for_project(db, project_id=project.id, user_id=user_id, doc_type="project", doc_id=project.id)

        year = date.today().year
        seq = _next_sequence(db, DOC_TYPE_OFFER_NUMBERING, year)
        project.offer_number = format_document_number(profile.offer_prefix, year, seq, profile.document_number_padding)
        if not project.offer_terms_snapshot_title or not project.offer_terms_snapshot_body:
            template = resolve_terms_template(
                db,
                profile=profile,
                client=project.client,
                doc_type=DOC_TYPE_OFFER,
                lang=lang,
            )
            project.offer_terms_snapshot_title = template.title
            project.offer_terms_snapshot_body = template.body_text
            _create_audit_event(
                db,
                event_type="offer_terms_snapshotted_on_issue",
                user_id=user_id,
                entity_type="project",
                entity_id=project.id,
                details={"template_id": template.id, "version": template.version},
            )
        project.offer_status = STATUS_ISSUED
        db.add(project)

        _create_audit_event(
            db,
            event_type="offer_issued",
            user_id=user_id,
            entity_type="project",
            entity_id=project.id,
            details={"doc_number": project.offer_number, "year": year, "seq": seq},
        )
        logger.info(
            "event=offer_issued doc_id=%s doc_number=%s user_id=%s year=%s seq=%s",
            project.id,
            project.offer_number,
            user_id,
            year,
            seq,
        )
        db.commit()
        db.refresh(project)
        return project
    except IntegrityError as exc:
        db.rollback()
        raise NumberingConflictError("Offer number already issued") from exc


def finalize_invoice(db: Session, invoice_id: int, user_id: str | None, profile: CompanyProfile, lang: str | None = None) -> Invoice:
    try:
        _lock_for_issuance(db)
        invoice = db.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")

        if invoice.status == STATUS_ISSUED and invoice.invoice_number:
            db.commit()
            return invoice

        _check_floor_policy_for_project(db, project_id=invoice.project_id, user_id=user_id, doc_type="invoice", doc_id=invoice.id)

        year = date.today().year
        seq = _next_sequence(db, DOC_TYPE_INVOICE_NUMBERING, year)
        invoice.invoice_number = format_document_number(
            profile.invoice_prefix,
            year,
            seq,
            profile.document_number_padding,
        )
        invoice.issue_date = invoice.issue_date or date.today()
        if not invoice.invoice_terms_snapshot_title or not invoice.invoice_terms_snapshot_body:
            template = resolve_terms_template(
                db,
                profile=profile,
                client=invoice.project.client,
                doc_type=DOC_TYPE_INVOICE,
                lang=lang,
            )
            invoice.invoice_terms_snapshot_title = template.title
            invoice.invoice_terms_snapshot_body = template.body_text
            _create_audit_event(
                db,
                event_type="invoice_terms_snapshotted_on_issue",
                user_id=user_id,
                entity_type="invoice",
                entity_id=invoice.id,
                details={"template_id": template.id, "version": template.version},
            )
        invoice.status = STATUS_ISSUED
        db.add(invoice)

        _create_audit_event(
            db,
            event_type="invoice_issued",
            user_id=user_id,
            entity_type="invoice",
            entity_id=invoice.id,
            details={"doc_number": invoice.invoice_number, "year": year, "seq": seq},
        )
        logger.info(
            "event=invoice_issued doc_id=%s doc_number=%s user_id=%s year=%s seq=%s",
            invoice.id,
            invoice.invoice_number,
            user_id,
            year,
            seq,
        )
        db.commit()
        db.refresh(invoice)
        return invoice
    except IntegrityError as exc:
        db.rollback()
        raise NumberingConflictError("Invoice number already issued") from exc
