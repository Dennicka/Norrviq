from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.commercial_snapshot import CommercialSnapshot
from app.models.invoice import Invoice
from app.models.project import Project

DOC_TYPE_OFFER = "OFFER"
DOC_TYPE_INVOICE = "INVOICE"


class CommercialSnapshotWriteError(ValueError):
    pass


def _norm(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, list):
        return [_norm(v) for v in value]
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    return value


def _document_is_draft(db: Session, *, doc_type: str, doc_id: int) -> bool:
    if doc_type == DOC_TYPE_OFFER:
        project = db.get(Project, doc_id)
        return bool(project and project.offer_status == "draft")
    invoice = db.get(Invoice, doc_id)
    return bool(invoice and invoice.status == "draft")


def write_commercial_snapshot(db: Session, doc_type: str, doc_id: int, commercial_model) -> int:
    existing = (
        db.query(CommercialSnapshot)
        .filter(CommercialSnapshot.doc_type == doc_type, CommercialSnapshot.doc_id == doc_id)
        .first()
    )
    if existing:
        return existing.id
    if not _document_is_draft(db, doc_type=doc_type, doc_id=doc_id):
        raise CommercialSnapshotWriteError("Snapshot can be created only for draft document")

    payload = {
        "mode": commercial_model.mode,
        "segment": getattr(commercial_model, "segment", "ANY"),
        "currency": "SEK",
        "m2_basis": (commercial_model.units or {}).get("m2_basis"),
        "units": commercial_model.units,
        "rates": commercial_model.rate,
        "totals": {
            "price_ex_vat": commercial_model.price_ex_vat,
            "vat_amount": commercial_model.vat_amount,
            "price_inc_vat": commercial_model.price_inc_vat,
        },
        "line_items": commercial_model.line_items,
    }

    snap = CommercialSnapshot(
        doc_type=doc_type,
        doc_id=doc_id,
        mode=payload["mode"],
        segment=payload["segment"],
        currency=payload["currency"],
        m2_basis=payload["m2_basis"],
        units_json=json.dumps(_norm(payload["units"]), ensure_ascii=False, sort_keys=True),
        rates_json=json.dumps(_norm(payload["rates"]), ensure_ascii=False, sort_keys=True),
        totals_json=json.dumps(_norm(payload["totals"]), ensure_ascii=False, sort_keys=True),
        line_items_json=json.dumps(_norm(payload["line_items"]), ensure_ascii=False, sort_keys=True),
    )
    db.add(snap)
    db.flush()
    return snap.id


def read_commercial_snapshot(db: Session, *, doc_type: str, doc_id: int) -> dict | None:
    snap = (
        db.query(CommercialSnapshot)
        .filter(CommercialSnapshot.doc_type == doc_type, CommercialSnapshot.doc_id == doc_id)
        .first()
    )
    if not snap:
        return None
    return {
        "id": snap.id,
        "mode": snap.mode,
        "segment": snap.segment,
        "currency": snap.currency,
        "m2_basis": snap.m2_basis,
        "units": json.loads(snap.units_json),
        "rates": json.loads(snap.rates_json),
        "totals": json.loads(snap.totals_json),
        "line_items": json.loads(snap.line_items_json),
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }
