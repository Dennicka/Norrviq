import logging
import random
import time
from datetime import date
from decimal import Decimal
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_event
from app.models.audit_event import AuditEvent
from app.models.company_profile import CompanyProfile
from app.models.document_sequence import DocumentSequence
from app.models.invoice import Invoice
from app.models.rot_case import RotCase
from app.models.pricing_policy import get_or_create_pricing_policy
from app.models.project import Project
from app.services.pricing import compute_pricing_scenarios, evaluate_floor
from app.services.offer_commercial import compute_offer_commercial, serialize_offer_commercial
from app.services.invoice_commercial import compute_invoice_commercial
from app.services.commercial_snapshot import DOC_TYPE_INVOICE as SNAP_INVOICE, DOC_TYPE_OFFER as SNAP_OFFER, write_commercial_snapshot
from app.services.pricing_consistency import validate_pricing_consistency
from app.services.completeness import compute_completeness
from app.services.terms_templates import DOC_TYPE_INVOICE, DOC_TYPE_OFFER, resolve_terms_template
from app.services.invoice_lines import recalculate_invoice_totals

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


class CompletenessViolationError(RuntimeError):
    def __init__(self, *, doc_type: str, doc_id: int, project_id: int, score: int, missing: list[dict]):
        super().__init__("Нельзя выпустить документ: недостаточно данных")
        self.doc_type = doc_type
        self.doc_id = doc_id
        self.project_id = project_id
        self.score = score
        self.missing = missing

MAX_NUMBERING_RETRIES = 10


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



def _check_completeness_for_project(db: Session, *, project_id: int, mode: str, user_id: str | None, doc_type: str, doc_id: int) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found")

    segment = project.client.client_segment if project.client and project.client.client_segment else "ANY"
    policy = get_or_create_pricing_policy(db)
    report = compute_completeness(db, project_id, mode=mode, segment=segment, lang="ru")
    if policy.warn_only_mode:
        return
    if mode in {"FIXED_TOTAL", "PER_M2", "PER_ROOM"} and not report.can_issue_mode:
        missing = [
            {"check_key": item.check_key, "severity": item.severity, "message": item.message, "hint_link": item.hint_link}
            for item in report.missing[:3]
        ]
        _create_audit_event(
            db,
            event_type="completeness_blocked_issue",
            user_id=user_id,
            entity_type=doc_type,
            entity_id=doc_id,
            details={"doc_type": doc_type, "doc_id": doc_id, "project_id": project_id, "mode": mode, "score": report.score, "missing": missing},
        )
        raise CompletenessViolationError(doc_type=doc_type, doc_id=doc_id, project_id=project_id, score=report.score, missing=missing)

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
    log_event(
        db,
        None,
        event_type,
        entity_type=entity_type.upper(),
        entity_id=entity_id,
        metadata={"user_id": user_id, **details},
    )
    db.add(
        AuditEvent(
            event_type=event_type,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details=str(details),
        )
    )


def _is_numbering_integrity_error(exc: IntegrityError) -> bool:
    return True


def finalize_offer(db: Session, project_id: int, user_id: str | None, profile: CompanyProfile, lang: str | None = None) -> Project:
    try:
        _lock_for_issuance(db)
        project = db.get(Project, project_id)
        if not project:
            raise ValueError("Project not found")

        if project.offer_status == STATUS_ISSUED and project.offer_number:
            db.commit()
            return project

        selected_mode = project.pricing.mode if project.pricing else "HOURLY"
        _check_completeness_for_project(db, project_id=project.id, mode=selected_mode, user_id=user_id, doc_type="project", doc_id=project.id)
        _check_floor_policy_for_project(db, project_id=project.id, user_id=user_id, doc_type="project", doc_id=project.id)
        commercial = compute_offer_commercial(db, project.id, lang=lang or "sv")
        consistency = validate_pricing_consistency(db, project.id, "OFFER", project.id)
        if not consistency.ok:
            _create_audit_event(
                db,
                event_type="pricing_consistency_failed",
                user_id=user_id,
                entity_type="project",
                entity_id=project.id,
                details={"doc_type": "OFFER", "project_id": project.id, "errors": consistency.errors},
            )
            raise ValueError("Offer totals mismatch pricing scenario")
        snapshot_id = write_commercial_snapshot(db, SNAP_OFFER, project.id, commercial)
        _create_audit_event(
            db,
            event_type="commercial_snapshot_written",
            user_id=user_id,
            entity_type="project",
            entity_id=project.id,
            details={"doc_type": "OFFER", "doc_id": project.id, "mode": commercial.mode, "snapshot_id": snapshot_id},
        )

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
        project.offer_commercial_snapshot = serialize_offer_commercial(commercial)
        project.offer_status = STATUS_ISSUED
        db.add(project)

        _create_audit_event(
            db,
            event_type="offer_issued",
            user_id=user_id,
            entity_type="project",
            entity_id=project.id,
            details={"doc_number": project.offer_number, "year": year, "seq": seq, "mode": commercial.mode, "price_ex_vat": str(commercial.price_ex_vat)},
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
    for attempt in range(MAX_NUMBERING_RETRIES):
        try:
            _lock_for_issuance(db)
            invoice = db.get(Invoice, invoice_id)
            if not invoice:
                raise ValueError("Invoice not found")

            if invoice.status == STATUS_ISSUED and invoice.invoice_number:
                db.commit()
                return invoice

            selected_mode = invoice.project.pricing.mode if invoice.project and invoice.project.pricing else "HOURLY"
            _check_completeness_for_project(db, project_id=invoice.project_id, mode=selected_mode, user_id=user_id, doc_type="invoice", doc_id=invoice.id)
            _check_floor_policy_for_project(db, project_id=invoice.project_id, user_id=user_id, doc_type="invoice", doc_id=invoice.id)

            recalculate_invoice_totals(db, invoice.id, user_id=user_id)
            has_material_lines = any((line.kind == "MATERIAL") for line in invoice.lines)
            pricing_includes_materials = bool(invoice.project and invoice.project.pricing and invoice.project.pricing.include_materials)
            if has_material_lines and not pricing_includes_materials:
                raise ValueError("Enable include_materials in pricing or remove material lines")
            commercial = compute_invoice_commercial(db, invoice.project_id, invoice.id)
            consistency = validate_pricing_consistency(db, invoice.project_id, "INVOICE", invoice.id)
            if not consistency.ok:
                _create_audit_event(
                    db,
                    event_type="pricing_consistency_failed",
                    user_id=user_id,
                    entity_type="invoice",
                    entity_id=invoice.id,
                    details={"doc_type": "INVOICE", "project_id": invoice.project_id, "errors": consistency.errors},
                )
                raise ValueError("Invoice totals mismatch pricing scenario")
            if abs(Decimal(str(invoice.subtotal_ex_vat or 0)) - commercial.price_ex_vat) > Decimal("0.01"):
                raise ValueError("Invoice totals mismatch pricing scenario")
            expected_vat = Decimal(str(invoice.subtotal_ex_vat or 0)) * Decimal(str(commercial.vat_rot_breakdown.get("vat_rate_pct") or 25)) / Decimal("100")
            expected_vat = expected_vat.quantize(Decimal("0.01"))
            if abs(Decimal(str(invoice.vat_total or 0)) - expected_vat) > Decimal("0.01"):
                raise ValueError("Invoice totals mismatch pricing scenario")
            rot_case = db.query(RotCase).filter(RotCase.invoice_id == invoice.id).first()

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
            invoice.commercial_mode_snapshot = commercial.mode
            invoice.units_snapshot = json.dumps(commercial.units, ensure_ascii=False, sort_keys=True, default=str)
            invoice.rates_snapshot = json.dumps(commercial.rate, ensure_ascii=False, sort_keys=True, default=str)
            invoice.subtotal_ex_vat_snapshot = invoice.subtotal_ex_vat
            invoice.vat_total_snapshot = invoice.vat_total
            invoice.total_inc_vat_snapshot = invoice.total_inc_vat
            invoice.rot_snapshot_enabled = bool(rot_case and rot_case.is_enabled)
            invoice.rot_snapshot_pct = rot_case.rot_pct if rot_case else 0
            invoice.rot_snapshot_eligible_labor_ex_vat = invoice.labour_ex_vat
            invoice.rot_snapshot_amount = invoice.rot_amount
            snapshot_id = write_commercial_snapshot(db, SNAP_INVOICE, invoice.id, commercial)
            invoice.status = STATUS_ISSUED
            _create_audit_event(
                db,
                event_type="commercial_snapshot_written",
                user_id=user_id,
                entity_type="invoice",
                entity_id=invoice.id,
                details={"doc_type": "INVOICE", "doc_id": invoice.id, "mode": commercial.mode, "snapshot_id": snapshot_id},
            )
            db.add(invoice)

            _create_audit_event(
                db,
                event_type="rot_snapshot_on_issue",
                user_id=user_id,
                entity_type="invoice",
                entity_id=invoice.id,
                details={
                    "enabled": invoice.rot_snapshot_enabled,
                    "pct": str(invoice.rot_snapshot_pct),
                    "eligible": str(invoice.rot_snapshot_eligible_labor_ex_vat),
                    "amount": str(invoice.rot_snapshot_amount),
                },
            )

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
            if not _is_numbering_integrity_error(exc):
                raise
            if attempt == MAX_NUMBERING_RETRIES - 1:
                raise NumberingConflictError("Could not allocate unique invoice number after retries") from exc
            time.sleep(0.002 + random.random() * 0.01)

    raise NumberingConflictError("Could not allocate unique invoice number after retries")
