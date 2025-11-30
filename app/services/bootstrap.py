from sqlalchemy.orm import Session

from app.models.cost import CostCategory
from app.models.legal_note import LegalNote


def ensure_default_cost_categories(db: Session) -> None:
    """
    Создаёт базовые категории расходов, если их ещё нет.
    Коды: MATERIALS, FUEL, PARKING, RENT, OTHER.
    """
    defaults = [
        ("MATERIALS", "Материалы", "Materialkostnader"),
        ("FUEL", "Топливо", "Bränsle"),
        ("PARKING", "Парковка", "Parkering"),
        ("RENT", "Аренда", "Hyra"),
        ("OTHER", "Прочее", "Övrigt"),
    ]
    for code, name_ru, name_sv in defaults:
        if not db.query(CostCategory).filter_by(code=code).first():
            db.add(CostCategory(code=code, name_ru=name_ru, name_sv=name_sv))
    db.commit()


def ensure_default_legal_notes(db: Session) -> None:
    """
    Создаёт базовые юридические заметки по ROT/MOMS,
    если таблица пустая.
    """
    if db.query(LegalNote).count() > 0:
        return

    notes = [
        LegalNote(
            code="ROT_BASICS",
            title_ru="Основы ROT-вычета",
            text_ru="ROT — это налоговый вычет на ремонт/отделку для частных лиц в Швеции...",
            title_sv="Grunderna för ROT-avdrag",
            text_sv="ROT är ett skatteavdrag för renovering och underhåll för privatpersoner i Sverige...",
        ),
        LegalNote(
            code="MOMS_BASICS",
            title_ru="MOMS для строительных работ",
            text_ru="Стандартная ставка MOMS для byggtjänster — 25 %. В смете MOMS считается от трудовой части...",
            title_sv="MOMS för byggtjänster",
            text_sv="Standardmomsen för byggtjänster är 25 %. I kalkylen beräknas MOMS på arbetsdelen...",
        ),
    ]
    for note in notes:
        db.add(note)
    db.commit()
