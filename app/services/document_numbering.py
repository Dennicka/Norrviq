import json
import logging
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.company_profile import CompanyProfile
from app.models.document_sequence import DocumentSequence
from app.models.invoice import Invoice
from app.models.project import Project

logger = logging.getLogger("uvicorn.error")

DOC_TYPE_OFFER = "offer"
DOC_TYPE_INVOICE = "invoice"
STATUS_DRAFT = "draft"
STATUS_ISSUED = "issued"


class NumberingConflictError(RuntimeError):
    pass


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


def finalize_offer(db: Session, project_id: int, user_id: str | None, profile: CompanyProfile) -> Project:
    try:
        _lock_for_issuance(db)
        project = db.get(Project, project_id)
        if not project:
            raise ValueError("Project not found")

        if project.offer_status == STATUS_ISSUED and project.offer_number:
            db.commit()
            return project

        year = date.today().year
        seq = _next_sequence(db, DOC_TYPE_OFFER, year)
        project.offer_number = format_document_number(profile.offer_prefix, year, seq, profile.document_number_padding)
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


def finalize_invoice(db: Session, invoice_id: int, user_id: str | None, profile: CompanyProfile) -> Invoice:
    try:
        _lock_for_issuance(db)
        invoice = db.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")

        if invoice.status == STATUS_ISSUED and invoice.invoice_number:
            db.commit()
            return invoice

        year = date.today().year
        seq = _next_sequence(db, DOC_TYPE_INVOICE, year)
        invoice.invoice_number = format_document_number(
            profile.invoice_prefix,
            year,
            seq,
            profile.document_number_padding,
        )
        invoice.status = STATUS_ISSUED
        invoice.issue_date = invoice.issue_date or date.today()
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
