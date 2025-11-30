from sqlalchemy import Column, Integer, String, Text

from app.db import Base


class LegalNote(Base):
    __tablename__ = "legal_notes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    title_ru = Column(String(255), nullable=False)
    text_ru = Column(Text, nullable=False)
    title_sv = Column(String(255), nullable=False)
    text_sv = Column(Text, nullable=False)
