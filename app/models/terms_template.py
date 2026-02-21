from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint, func

from app.db import Base


class TermsTemplate(Base):
    __tablename__ = "terms_templates"
    __table_args__ = (
        UniqueConstraint("segment", "doc_type", "lang", "version", name="uq_terms_templates_segment_doc_lang_version"),
    )

    id = Column(Integer, primary_key=True, index=True)
    segment = Column(String(16), nullable=False)
    doc_type = Column(String(16), nullable=False)
    lang = Column(String(8), nullable=False, default="sv")
    version = Column(Integer, nullable=False, default=1)
    title = Column(Text, nullable=False)
    body_text = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
