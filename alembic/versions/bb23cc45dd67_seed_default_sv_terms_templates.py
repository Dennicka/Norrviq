"""seed default sv terms templates

Revision ID: bb23cc45dd67
Revises: aa12bb34cc56
Create Date: 2026-02-21 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "bb23cc45dd67"
down_revision = "aa12bb34cc56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(1) FROM terms_templates")).scalar() or 0
    if count:
        return

    defaults = [
        (
            "B2C",
            "OFFER",
            "sv",
            1,
            "Offertvillkor för privatkund",
            "Offerten gäller i 30 dagar. Arbetet utförs fackmässigt enligt överenskommen omfattning.",
        ),
        (
            "BRF",
            "OFFER",
            "sv",
            1,
            "Offertvillkor för bostadsrättsförening",
            "Arbetet utförs enligt beställning och i samråd med föreningens kontaktperson.",
        ),
        (
            "B2B",
            "OFFER",
            "sv",
            1,
            "Offertvillkor för företag",
            "Offerten gäller i 30 dagar. ÄTA-arbeten faktureras enligt överenskommen tim- eller enhetsprislista.",
        ),
        (
            "B2C",
            "INVOICE",
            "sv",
            1,
            "Fakturavillkor för privatkund",
            "Betalningsvillkor 10 dagar. Dröjsmålsränta och påminnelseavgift debiteras enligt lag.",
        ),
        (
            "BRF",
            "INVOICE",
            "sv",
            1,
            "Fakturavillkor för bostadsrättsförening",
            "Betalning enligt avtalade villkor. Ange fakturanummer vid betalning.",
        ),
        (
            "B2B",
            "INVOICE",
            "sv",
            1,
            "Fakturavillkor för företag",
            "Betalningsvillkor 30 dagar netto om inget annat avtalats skriftligen.",
        ),
    ]

    conn.execute(
        sa.text(
            """
            INSERT INTO terms_templates (segment, doc_type, lang, version, title, body_text, is_active)
            VALUES (:segment, :doc_type, :lang, :version, :title, :body_text, :is_active)
            """
        ),
        [
            {
                "segment": segment,
                "doc_type": doc_type,
                "lang": lang,
                "version": version,
                "title": title,
                "body_text": body_text,
                "is_active": True,
            }
            for segment, doc_type, lang, version, title, body_text in defaults
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM terms_templates
            WHERE version = 1
              AND lang = 'sv'
              AND (
                    (segment='B2C' AND doc_type='OFFER' AND title='Offertvillkor för privatkund') OR
                    (segment='BRF' AND doc_type='OFFER' AND title='Offertvillkor för bostadsrättsförening') OR
                    (segment='B2B' AND doc_type='OFFER' AND title='Offertvillkor för företag') OR
                    (segment='B2C' AND doc_type='INVOICE' AND title='Fakturavillkor för privatkund') OR
                    (segment='BRF' AND doc_type='INVOICE' AND title='Fakturavillkor för bostadsrättsförening') OR
                    (segment='B2B' AND doc_type='INVOICE' AND title='Fakturavillkor för företag')
              )
            """
        )
    )
