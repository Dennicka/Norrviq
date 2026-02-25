from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.invoice import Invoice
from app.services.terms_templates import DOC_TYPE_INVOICE, resolve_terms_template

SUPPORTED_LANGS = {"ru", "sv", "en"}


@dataclass(frozen=True)
class TermsResolution:
    title: str
    body: str
    requested_lang: str
    resolved_lang: str
    used_fallback: bool


def normalize_document_lang(lang: str | None, fallback: str = "sv") -> str:
    if lang in SUPPORTED_LANGS:
        return str(lang)
    return fallback


def invoice_render_lang(invoice: Invoice, request_lang: str | None = None) -> str:
    if invoice.status == "issued" and invoice.issued_lang_snapshot:
        return normalize_document_lang(invoice.issued_lang_snapshot)
    return normalize_document_lang(invoice.document_lang, fallback=normalize_document_lang(request_lang))


def resolve_invoice_terms(
    db: Session,
    *,
    profile: CompanyProfile,
    invoice: Invoice,
    requested_lang: str,
) -> TermsResolution:
    if invoice.status == "issued":
        resolved = invoice_render_lang(invoice, requested_lang)
        return TermsResolution(
            title=invoice.invoice_terms_snapshot_title or "",
            body=invoice.invoice_terms_snapshot_body or "",
            requested_lang=resolved,
            resolved_lang=resolved,
            used_fallback=False,
        )

    template = resolve_terms_template(
        db,
        profile=profile,
        client=invoice.project.client,
        doc_type=DOC_TYPE_INVOICE,
        lang=requested_lang,
    )
    resolved_lang = normalize_document_lang(template.lang)
    requested = normalize_document_lang(requested_lang)
    return TermsResolution(
        title=template.title,
        body=template.body_text,
        requested_lang=requested,
        resolved_lang=resolved_lang,
        used_fallback=requested != resolved_lang,
    )


def format_doc_date(value: date | None, lang: str) -> str:
    if not value:
        return ""
    if lang == "en":
        return value.strftime("%Y-%m-%d")
    return value.strftime("%d.%m.%Y")


def format_doc_money(value: Decimal | int | float | str | None, lang: str) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    normalized = f"{amount:,.2f}"  # 1,234.56
    if lang in {"ru", "sv"}:
        return normalized.replace(",", " ").replace(".", ",")
    return normalized
