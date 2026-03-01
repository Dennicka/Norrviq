from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from app.models.work_package import WorkPackageTemplate, WorkPackageTemplateItem


@dataclass(frozen=True)
class DefaultPackageItem:
    work_type_code: str
    basis_type: str
    coats: Decimal | None = None
    difficulty_factor: Decimal | None = None


@dataclass(frozen=True)
class DefaultPackageTemplate:
    code: str
    icon: str
    name_ru: str
    name_sv: str
    name_en: str
    description_ru: str
    description_sv: str
    description_en: str
    items: tuple[DefaultPackageItem, ...]


DEFAULT_WORK_PACKAGES: tuple[DefaultPackageTemplate, ...] = (
    DefaultPackageTemplate(
        code="PKG_PREP_FLOOR_COVER",
        icon="🛡️",
        name_ru="Защита пола",
        name_sv="Skydd av golv",
        name_en="Floor protection",
        description_ru="Плёнка/бумага для защиты пола перед работами.",
        description_sv="Plast/papper för att skydda golv före arbete.",
        description_en="Film/paper to protect floors before work.",
        items=(DefaultPackageItem(work_type_code="COVER_FLOOR_PAPER", basis_type="floor_area_m2"),),
    ),
    DefaultPackageTemplate(
        code="PKG_MASKING",
        icon="🎯",
        name_ru="Укрытие и малярная лента",
        name_sv="Maskering och tejp",
        name_en="Masking and tape",
        description_ru="Укрытие поверхностей и проклейка стыков.",
        description_sv="Maskering av ytor och tejpning av skarvar.",
        description_en="Masking surfaces and taping edges.",
        items=(DefaultPackageItem(work_type_code="MASKING_TAPE", basis_type="perimeter_m"),),
    ),
    DefaultPackageTemplate(
        code="PKG_SPOT_REPAIR",
        icon="🩹",
        name_ru="Заделка дыр",
        name_sv="Laga hål",
        name_en="Spot repair",
        description_ru="Локальный ремонт трещин и отверстий.",
        description_sv="Lokal lagning av sprickor och hål.",
        description_en="Local repair of cracks and holes.",
        items=(DefaultPackageItem(work_type_code="WALL_SPACKLE_LAYER_1", basis_type="wall_area_m2"),),
    ),
    DefaultPackageTemplate(
        code="PKG_SPACKLE_WALL_1",
        icon="🧱",
        name_ru="Шпаклевка стен 1 слой",
        name_sv="Spackla vägg 1 lager",
        name_en="Wall spackle 1 layer",
        description_ru="Базовый выравнивающий слой шпаклевки.",
        description_sv="Grundläggande utjämnande spackellager.",
        description_en="Base leveling putty layer.",
        items=(DefaultPackageItem(work_type_code="WALL_SPACKLE_LAYER_1", basis_type="wall_area_m2"),),
    ),
    DefaultPackageTemplate(
        code="PKG_SPACKLE_WALL_2",
        icon="🧱",
        name_ru="Шпаклевка стен 2 слой",
        name_sv="Spackla vägg 2 lager",
        name_en="Wall spackle 2 layers",
        description_ru="Финишный слой шпаклевки для подготовки под покраску.",
        description_sv="Finputsningslager för målning.",
        description_en="Finishing putty layer before painting.",
        items=(
            DefaultPackageItem(work_type_code="WALL_SPACKLE_LAYER_1", basis_type="wall_area_m2"),
            DefaultPackageItem(work_type_code="WALL_SPACKLE_LAYER_2", basis_type="wall_area_m2"),
            DefaultPackageItem(work_type_code="WALL_SANDING", basis_type="wall_area_m2"),
        ),
    ),
    DefaultPackageTemplate(
        code="PKG_SANDING_WALL",
        icon="🧽",
        name_ru="Шлифовка стен",
        name_sv="Slipning av vägg",
        name_en="Wall sanding",
        description_ru="Шлифовка после шпаклевки.",
        description_sv="Slipning efter spackling.",
        description_en="Sanding after putty.",
        items=(DefaultPackageItem(work_type_code="WALL_SANDING", basis_type="wall_area_m2"),),
    ),
    DefaultPackageTemplate(
        code="PKG_PRIMER_WALL",
        icon="🧴",
        name_ru="Грунт",
        name_sv="Primer",
        name_en="Primer",
        description_ru="Грунтование стен перед покраской.",
        description_sv="Grundning av väggar före målning.",
        description_en="Priming walls before painting.",
        items=(DefaultPackageItem(work_type_code="WALL_PAINT_PRIMER", basis_type="wall_area_m2"),),
    ),
    DefaultPackageTemplate(
        code="PKG_PAINT_WALL_2",
        icon="🎨",
        name_ru="Покраска стен 2 слоя",
        name_sv="Måla vägg 2 lager",
        name_en="Paint walls 2 coats",
        description_ru="Два финишных слоя краски на стены.",
        description_sv="Två färdiga lager färg på väggar.",
        description_en="Two final paint coats on walls.",
        items=(
            DefaultPackageItem(work_type_code="WALL_PAINT_COAT_1", basis_type="wall_area_m2"),
            DefaultPackageItem(work_type_code="WALL_PAINT_COAT_2", basis_type="wall_area_m2"),
        ),
    ),
    DefaultPackageTemplate(
        code="PKG_PAINT_CEILING_2",
        icon="🖌️",
        name_ru="Покраска потолка 2 слоя",
        name_sv="Måla tak 2 lager",
        name_en="Paint ceiling 2 coats",
        description_ru="Два слоя краски для потолка.",
        description_sv="Två lager färg för tak.",
        description_en="Two paint coats for ceiling.",
        items=(
            DefaultPackageItem(work_type_code="CEILING_PAINT_COAT_1", basis_type="ceiling_area_m2"),
            DefaultPackageItem(work_type_code="CEILING_PAINT_COAT_2", basis_type="ceiling_area_m2"),
        ),
    ),
    DefaultPackageTemplate(
        code="PKG_BASEBOARD",
        icon="📏",
        name_ru="Плинтуса",
        name_sv="Socklar",
        name_en="Baseboards",
        description_ru="Покраска/монтаж плинтусов при наличии.",
        description_sv="Målning/montering av socklar om de finns.",
        description_en="Paint/install baseboards when present.",
        items=(DefaultPackageItem(work_type_code="BASEBOARD_PAINT", basis_type="perimeter_m"),),
    ),
)


def package_label(template: WorkPackageTemplate, lang: str) -> str:
    if lang == "ru":
        return template.name_ru
    if lang == "en":
        return template.name_en
    return template.name_sv


def package_description(template: WorkPackageTemplate, lang: str) -> str:
    if lang == "ru":
        return template.description_ru or ""
    if lang == "en":
        return template.description_en or ""
    return template.description_sv or ""


def package_icon(package_code: str) -> str:
    return next((item.icon for item in DEFAULT_WORK_PACKAGES if item.code == package_code), "📦")


def ensure_default_packages(db: Session) -> None:
    existing_codes = {code for (code,) in db.query(WorkPackageTemplate.code).all()}
    changed = False

    for template in DEFAULT_WORK_PACKAGES:
        if template.code in existing_codes:
            continue
        row = WorkPackageTemplate(
            code=template.code,
            name_ru=template.name_ru,
            name_sv=template.name_sv,
            name_en=template.name_en,
            description_ru=template.description_ru,
            description_sv=template.description_sv,
            description_en=template.description_en,
            is_active=True,
        )
        db.add(row)
        db.flush()
        for sort_order, item in enumerate(template.items, start=1):
            db.add(
                WorkPackageTemplateItem(
                    template_id=row.id,
                    work_type_code=item.work_type_code,
                    scope_mode="PROJECT",
                    basis_type=item.basis_type,
                    pricing_mode="HOURLY",
                    coats=item.coats,
                    difficulty_factor=item.difficulty_factor or Decimal("1"),
                    sort_order=sort_order,
                )
            )
        changed = True

    if changed:
        db.commit()


def list_active_packages(db: Session) -> list[WorkPackageTemplate]:
    ensure_default_packages(db)
    return (
        db.query(WorkPackageTemplate)
        .options(selectinload(WorkPackageTemplate.items))
        .filter(WorkPackageTemplate.is_active.is_(True))
        .order_by(WorkPackageTemplate.id.asc())
        .all()
    )



def apply_package_to_project(db: Session, *, project_id: int, package_code: str) -> int:
    from app.services.work_packages_apply import apply_package

    summary = apply_package(
        db,
        project_id=project_id,
        package_code=package_code,
        scope_mode="WHOLE_PROJECT",
        selected_room_ids=[],
    )
    return summary.created_count + summary.updated_count
