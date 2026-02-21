from sqlalchemy.orm import Session

from app.models.terms_template import TermsTemplate
from app.services.terms_templates import create_versioned_template


def seed_terms_templates(db: Session) -> None:
    if db.query(TermsTemplate).count() > 0:
        return

    sv_templates = [
        ("B2C", "OFFER", "Allmänna villkor för offert (B2C)", "Arbetet utförs enligt överenskommen omfattning. Betalning enligt faktura."),
        ("BRF", "OFFER", "Allmänna villkor för offert (BRF)", "Arbetet utförs i samråd med styrelsen. ÄTA debiteras separat."),
        ("B2B", "OFFER", "Allmänna villkor för offert (B2B)", "Offerten gäller i 30 dagar. Fakturering sker enligt överenskommen plan."),
        ("B2C", "INVOICE", "Fakturavillkor (B2C)", "Betalningsvillkor 10 dagar. Dröjsmålsränta enligt räntelagen."),
        ("BRF", "INVOICE", "Fakturavillkor (BRF)", "Betalningsvillkor enligt avtal. Ange objektnummer vid betalning."),
        ("B2B", "INVOICE", "Fakturavillkor (B2B)", "Betalningsvillkor 30 dagar netto om inget annat avtalats."),
    ]
    for segment, doc_type, title, body in sv_templates:
        create_versioned_template(db, segment=segment, doc_type=doc_type, lang="sv", title=title, body_text=body)

    ru_templates = [
        ("B2C", "OFFER", "Условия оферты (B2C)", "Работы выполняются по согласованному объёму. Оплата по счёту."),
        ("B2C", "INVOICE", "Условия фактуры (B2C)", "Срок оплаты 10 дней. Пени начисляются по закону."),
    ]
    for segment, doc_type, title, body in ru_templates:
        create_versioned_template(db, segment=segment, doc_type=doc_type, lang="ru", title=title, body_text=body)

    db.commit()
