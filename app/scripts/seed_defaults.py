from __future__ import annotations

from decimal import Decimal

from app.db import SessionLocal
from app.models.material_catalog_item import MaterialCatalogItem
from app.models.material_norm import MaterialConsumptionNorm
from app.models.worktype import WorkType

WORKTYPES = [
    ("MASK_FLOOR", "Подготовка", "m2", "Защита пола", "Skydda golv", Decimal("0.05")),
    ("MASKING", "Подготовка", "m2", "Маскировка", "Maskering", Decimal("0.03")),
    ("SPOT_REPAIR", "Ремонт", "m2", "Локальный ремонт", "Lokal lagning", Decimal("0.10")),
    ("SKIM_WALL", "Шпаклевка", "m2", "Шпаклевка стен", "Spackla vägg", Decimal("0.16")),
    ("SAND_WALL", "Шлифовка", "m2", "Шлифовка стен", "Slipa vägg", Decimal("0.08")),
    ("PRIMER_WALL", "Покраска", "m2", "Грунт стен", "Grundmåla vägg", Decimal("0.07")),
    ("PAINT_WALL", "Покраска", "m2", "Покраска стен", "Måla vägg", Decimal("0.13")),
    ("PAINT_CEILING", "Покраска", "m2", "Покраска потолка", "Måla tak", Decimal("0.14")),
    ("PAINT_TRIM", "Покраска", "m", "Покраска плинтуса", "Måla list", Decimal("0.04")),
]

MATERIALS = [
    ("PAINT_WALL_STD", "Краска для стен", "L", Decimal("10"), Decimal("1290")),
    ("PAINT_CEILING_STD", "Краска для потолка", "L", Decimal("10"), Decimal("1190")),
    ("PRIMER_STD", "Грунтовка", "L", Decimal("10"), Decimal("890")),
    ("PUTTY_STD", "Шпаклевка", "kg", Decimal("20"), Decimal("420")),
    ("MASK_TAPE", "Малярная лента", "pcs", Decimal("1"), Decimal("45")),
    ("COVER_FILM", "Защитная пленка", "m2", Decimal("20"), Decimal("80")),
]

NORMS = [
    ("PAINT_WALL", "PAINT_WALL_STD", "Краска стен", "paint", Decimal("0.23"), "L", True),
    ("PAINT_CEILING", "PAINT_CEILING_STD", "Краска потолка", "paint", Decimal("0.20"), "L", True),
    ("PRIMER_WALL", "PRIMER_STD", "Грунтовка", "primer", Decimal("0.10"), "L", True),
    ("SKIM_WALL", "PUTTY_STD", "Шпаклевка", "filler", Decimal("1.20"), "kg", True),
    ("MASKING", "MASK_TAPE", "Малярная лента", "consumable", Decimal("0.20"), "pcs", False),
    ("MASK_FLOOR", "COVER_FILM", "Пленка", "consumable", Decimal("1.10"), "m2", False),
]


def seed_defaults() -> None:
    db = SessionLocal()
    try:
        material_by_code: dict[str, MaterialCatalogItem] = {}
        for code, category, unit, name_ru, name_sv, hours in WORKTYPES:
            row = db.query(WorkType).filter(WorkType.code == code).first() or WorkType(code=code, unit=unit, name_ru=name_ru, name_sv=name_sv, hours_per_unit=hours)
            row.category = category
            row.unit = unit
            row.name_ru = name_ru
            row.name_sv = name_sv
            row.description_ru = name_ru
            row.description_sv = name_sv
            row.hours_per_unit = hours
            row.is_active = True
            db.add(row)

        for code, name, unit, package_size, price in MATERIALS:
            material = db.query(MaterialCatalogItem).filter(MaterialCatalogItem.material_code == code).first() or MaterialCatalogItem(material_code=code, name=name, unit=unit, package_size=package_size, package_unit=unit, price_ex_vat=price, vat_rate_pct=Decimal("25"))
            material.name = name
            material.unit = unit
            material.package_size = package_size
            material.package_unit = unit
            material.price_ex_vat = price
            material.is_active = True
            db.add(material)
            db.flush()
            material_by_code[code] = material

        for work_code, mat_code, name, category, qty, unit, per_layer in NORMS:
            norm = db.query(MaterialConsumptionNorm).filter(MaterialConsumptionNorm.applies_to_work_type == work_code, MaterialConsumptionNorm.material_name == name).first() or MaterialConsumptionNorm(material_name=name, material_category=category, applies_to_work_type=work_code, consumption_value=qty, consumption_unit="per_1_m2", material_unit=unit, waste_percent=Decimal("10"))
            norm.work_type_code = work_code
            norm.material_catalog_item_id = material_by_code[mat_code].id
            norm.active = True
            norm.is_active = True
            norm.layers_multiplier_enabled = per_layer
            norm.coats_multiplier_mode = "use_work_coats" if per_layer else "none"
            norm.quantity_per_basis = qty
            norm.per_basis_qty = Decimal("1")
            norm.per_basis_unit = "m2"
            norm.consumption_qty = qty
            norm.consumption_value = qty
            norm.material_unit = unit
            norm.default_unit_price_sek = material_by_code[mat_code].price_ex_vat / material_by_code[mat_code].package_size
            db.add(norm)

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_defaults()
    print("Defaults seeded")
