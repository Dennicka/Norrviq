from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.company_profile import CompanyProfile
from app.models.terms_template import TermsTemplate

DOC_TYPE_OFFER = "OFFER"
DOC_TYPE_INVOICE = "INVOICE"
DEFAULT_LANG = "sv"
DEFAULT_SEGMENT = "B2C"


def create_versioned_template(
    db: Session,
    *,
    segment: str,
    doc_type: str,
    lang: str,
    title: str,
    body_text: str,
    is_active: bool = True,
) -> TermsTemplate:
    latest_version = (
        db.query(TermsTemplate.version)
        .filter(
            TermsTemplate.segment == segment,
            TermsTemplate.doc_type == doc_type,
            TermsTemplate.lang == lang,
        )
        .order_by(TermsTemplate.version.desc())
        .first()
    )
    next_version = (latest_version[0] if latest_version else 0) + 1
    template = TermsTemplate(
        segment=segment,
        doc_type=doc_type,
        lang=lang,
        version=next_version,
        title=title,
        body_text=body_text,
        is_active=is_active,
    )
    db.add(template)
    db.flush()
    return template


def resolve_terms_template(
    db: Session,
    *,
    profile: CompanyProfile,
    client: Client | None,
    doc_type: str,
    lang: str | None,
) -> TermsTemplate | None:
    effective_lang = lang if lang in {"sv", "ru", "en"} else DEFAULT_LANG

    default_template_id = (
        profile.default_offer_terms_template_id
        if doc_type == DOC_TYPE_OFFER
        else profile.default_invoice_terms_template_id
    )
    if default_template_id:
        default_template = db.get(TermsTemplate, default_template_id)
        if default_template and default_template.is_active:
            return default_template

    segment = (client.client_segment if client else None) or DEFAULT_SEGMENT

    template = (
        db.query(TermsTemplate)
        .filter(
            TermsTemplate.segment == segment,
            TermsTemplate.doc_type == doc_type,
            TermsTemplate.lang == effective_lang,
            TermsTemplate.is_active.is_(True),
        )
        .order_by(TermsTemplate.version.desc())
        .first()
    )
    if template or effective_lang == DEFAULT_LANG:
        return template

    return (
        db.query(TermsTemplate)
        .filter(
            TermsTemplate.segment == segment,
            TermsTemplate.doc_type == doc_type,
            TermsTemplate.lang == DEFAULT_LANG,
            TermsTemplate.is_active.is_(True),
        )
        .order_by(TermsTemplate.version.desc())
        .first()
    )
