from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cost import CostCategory
from app.models.legal_note import LegalNote
from app.models.worktype import WorkType
from app.models.speed_profile import SpeedProfile


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


def ensure_default_worktypes(db: Session) -> None:
    defaults = [
        {
            "code": "COVER_FLOOR_PAPER",
            "category": "Подготовка",
            "unit": "m2",
            "name_ru": "Застил пола бумагой/картоном",
            "name_sv": "Täck golv med papper/kartong",
            "description_ru": "Защита пола перед работами",
            "description_sv": "Skyddar golv inför arbetet",
            "minutes": 4,
        },
        {
            "code": "MASKING_TAPE",
            "category": "Подготовка",
            "unit": "m",
            "name_ru": "Наклейка малярного скотча",
            "name_sv": "Maskeringstejp",
            "description_ru": "Проклейка стыков и углов",
            "description_sv": "Maskering av kanter och lister",
            "minutes": 1,
        },
        {
            "code": "WALL_SPACKLE_LAYER_1",
            "category": "Шпаклёвка",
            "unit": "m2",
            "name_ru": "Шпаклёвка стен, 1 слой",
            "name_sv": "Spackling väggar, lager 1",
            "description_ru": "Первый слой шпаклёвки стен",
            "description_sv": "Första lagret spackel på vägg",
            "minutes": 10,
        },
        {
            "code": "WALL_SPACKLE_LAYER_2",
            "category": "Шпаклёвка",
            "unit": "m2",
            "name_ru": "Шпаклёвка стен, 2 слой",
            "name_sv": "Spackling väggar, lager 2",
            "description_ru": "Второй слой шпаклёвки стен",
            "description_sv": "Andra lagret spackel på vägg",
            "minutes": 8,
        },
        {
            "code": "WALL_SPACKLE_LAYER_3",
            "category": "Шпаклёвка",
            "unit": "m2",
            "name_ru": "Шпаклёвка стен, 3 слой",
            "name_sv": "Spackling väggar, lager 3",
            "description_ru": "Финишный слой шпаклёвки стен",
            "description_sv": "Tredje lagret spackel på vägg",
            "minutes": 8,
        },
        {
            "code": "CEILING_SPACKLE_LAYER_1",
            "category": "Шпаклёвка",
            "unit": "m2",
            "name_ru": "Шпаклёвка потолка, 1 слой",
            "name_sv": "Spackling tak, lager 1",
            "description_ru": "Первый слой шпаклёвки потолка",
            "description_sv": "Första lagret spackel på tak",
            "minutes": 12,
        },
        {
            "code": "CEILING_SPACKLE_LAYER_2",
            "category": "Шпаклёвка",
            "unit": "m2",
            "name_ru": "Шпаклёвка потолка, 2 слой",
            "name_sv": "Spackling tak, lager 2",
            "description_ru": "Второй слой шпаклёвки потолка",
            "description_sv": "Andra lagret spackel på tak",
            "minutes": 10,
        },
        {
            "code": "WALL_SANDING",
            "category": "Шлифовка",
            "unit": "m2",
            "name_ru": "Шлифовка стен",
            "name_sv": "Slipning väggar",
            "description_ru": "Шлифовка подготовленных стен",
            "description_sv": "Slipning av förberedda väggar",
            "minutes": 6,
        },
        {
            "code": "CEILING_SANDING",
            "category": "Шлифовка",
            "unit": "m2",
            "name_ru": "Шлифовка потолка",
            "name_sv": "Slipning tak",
            "description_ru": "Шлифовка подготовленного потолка",
            "description_sv": "Slipning av förberett tak",
            "minutes": 7,
        },
        {
            "code": "WALL_PAINT_PRIMER",
            "category": "Покраска",
            "unit": "m2",
            "name_ru": "Грунт стен перед покраской",
            "name_sv": "Primer vägg",
            "description_ru": "Грунтование стен",
            "description_sv": "Grundning av väggar",
            "minutes": 6,
        },
        {
            "code": "WALL_PAINT_COAT_1",
            "category": "Покраска",
            "unit": "m2",
            "name_ru": "Покраска стен, 1 слой",
            "name_sv": "Målning väggar, lager 1",
            "description_ru": "Первый слой краски по стенам",
            "description_sv": "Första färglagret på vägg",
            "minutes": 8,
        },
        {
            "code": "WALL_PAINT_COAT_2",
            "category": "Покраска",
            "unit": "m2",
            "name_ru": "Покраска стен, 2 слой",
            "name_sv": "Målning väggar, lager 2",
            "description_ru": "Второй слой краски по стенам",
            "description_sv": "Andra färglagret på vägg",
            "minutes": 8,
        },
        {
            "code": "CEILING_PAINT_PRIMER",
            "category": "Покраска",
            "unit": "m2",
            "name_ru": "Грунт потолка перед покраской",
            "name_sv": "Primer tak",
            "description_ru": "Грунтование потолка",
            "description_sv": "Grundning av tak",
            "minutes": 7,
        },
        {
            "code": "CEILING_PAINT_COAT_1",
            "category": "Покраска",
            "unit": "m2",
            "name_ru": "Покраска потолка, 1 слой",
            "name_sv": "Målning tak, lager 1",
            "description_ru": "Первый слой краски по потолку",
            "description_sv": "Första färglagret på tak",
            "minutes": 9,
        },
        {
            "code": "CEILING_PAINT_COAT_2",
            "category": "Покраска",
            "unit": "m2",
            "name_ru": "Покраска потолка, 2 слой",
            "name_sv": "Målning tak, lager 2",
            "description_ru": "Второй слой краски по потолку",
            "description_sv": "Andra färglagret på tak",
            "minutes": 9,
        },
        {
            "code": "BASEBOARD_PAINT",
            "category": "Покраска",
            "unit": "m",
            "name_ru": "Покраска плинтуса",
            "name_sv": "Målning sockel",
            "description_ru": "Покраска плинтусов",
            "description_sv": "Målning av sockellister",
            "minutes": 3,
        },
        {
            "code": "DOOR_PAINT_ONE_SIDE",
            "category": "Покраска",
            "unit": "door",
            "name_ru": "Покраска двери, одна сторона",
            "name_sv": "Målning dörr, en sida",
            "description_ru": "Покраска одной стороны двери",
            "description_sv": "Målning av ena sidan av dörr",
            "minutes": 30,
        },
        {
            "code": "DOOR_PAINT_BOTH_SIDES",
            "category": "Покраска",
            "unit": "door",
            "name_ru": "Покраска двери, обе стороны",
            "name_sv": "Målning dörr, båda sidor",
            "description_ru": "Покраска двух сторон двери",
            "description_sv": "Målning av båda sidor av dörr",
            "minutes": 50,
        },
        {
            "code": "WINDOW_PAINT_STANDARD",
            "category": "Покраска",
            "unit": "window",
            "name_ru": "Покраска окна, стандарт",
            "name_sv": "Målning fönster, standard",
            "description_ru": "Стандартное окно",
            "description_sv": "Standardfönster",
            "minutes": 45,
        },
        {
            "code": "RADIATOR_SMALL_PAINT",
            "category": "Покраска",
            "unit": "radiator",
            "name_ru": "Покраска радиатора, малый",
            "name_sv": "Målning radiator, liten",
            "description_ru": "Небольшой радиатор",
            "description_sv": "Mindre radiator",
            "minutes": 35,
        },
        {
            "code": "RADIATOR_LARGE_PAINT",
            "category": "Покраска",
            "unit": "radiator",
            "name_ru": "Покраска радиатора, большой",
            "name_sv": "Målning radiator, stor",
            "description_ru": "Крупный радиатор",
            "description_sv": "Större radiator",
            "minutes": 50,
        },
        {
            "code": "ROOM_CLEANUP_BASIC",
            "category": "Уборка",
            "unit": "room",
            "name_ru": "Базовая уборка комнаты",
            "name_sv": "Grundstädning rum",
            "description_ru": "Сбор мусора, пылесос, влажная уборка",
            "description_sv": "Grundläggande städning av rum",
            "minutes": 40,
        },
    ]

    for data in defaults:
        existing = db.query(WorkType).filter_by(code=data["code"]).first()
        hours = (
            Decimal(str(data.get("minutes"))) / Decimal(60)
            if data.get("minutes") is not None
            else None
        )
        base_difficulty = Decimal(str(data.get("base_difficulty_factor", "1")))

        if existing:
            existing.category = data.get("category")
            existing.unit = data.get("unit")
            existing.name_ru = data.get("name_ru")
            existing.name_sv = data.get("name_sv")
            existing.description_ru = data.get("description_ru")
            existing.description_sv = data.get("description_sv")
            existing.hours_per_unit = hours
            existing.base_difficulty_factor = base_difficulty
        else:
            db.add(
                WorkType(
                    code=data["code"],
                    category=data.get("category"),
                    unit=data.get("unit"),
                    name_ru=data.get("name_ru"),
                    name_sv=data.get("name_sv"),
                    description_ru=data.get("description_ru"),
                    description_sv=data.get("description_sv"),
                    hours_per_unit=hours,
                    base_difficulty_factor=base_difficulty,
                    is_active=True,
                )
            )

    db.commit()


def ensure_default_speed_profiles(db: Session) -> None:
    defaults = [
        ("SLOW", "Медленно", "Långsam", Decimal("1.200")),
        ("MEDIUM", "Средне", "Normal", Decimal("1.000")),
        ("FAST", "Быстро", "Snabb", Decimal("0.850")),
    ]
    for code, name_ru, name_sv, multiplier in defaults:
        existing = db.query(SpeedProfile).filter(SpeedProfile.code == code).first()
        if existing is None:
            db.add(SpeedProfile(code=code, name_ru=name_ru, name_sv=name_sv, multiplier=multiplier, is_active=True))
    db.commit()
