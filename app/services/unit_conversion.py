from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

UNIT_Q = Decimal("0.0001")


class UnitDimension(str, Enum):
    VOLUME = "VOLUME"
    MASS = "MASS"
    LENGTH = "LENGTH"
    AREA = "AREA"
    COUNT = "COUNT"
    UNKNOWN = "UNKNOWN"


class UnitConversionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_UNIT_ALIASES = {
    "l": "l",
    "liter": "l",
    "litre": "l",
    "ml": "ml",
    "kg": "kg",
    "g": "g",
    "m": "m",
    "cm": "cm",
    "mm": "mm",
    "m2": "m2",
    "sqm": "m2",
    "m²": "m2",
    "pcs": "pcs",
    "pc": "pcs",
    "st": "pcs",
    "шт": "pcs",
    "pack": "pack",
    "paket": "pack",
}


_DIMENSION_BY_UNIT = {
    "l": UnitDimension.VOLUME,
    "ml": UnitDimension.VOLUME,
    "kg": UnitDimension.MASS,
    "g": UnitDimension.MASS,
    "m": UnitDimension.LENGTH,
    "cm": UnitDimension.LENGTH,
    "mm": UnitDimension.LENGTH,
    "m2": UnitDimension.AREA,
    "pcs": UnitDimension.COUNT,
    "pack": UnitDimension.COUNT,
}


def normalize_unit(u: str | None) -> str | None:
    if u is None:
        return None
    normalized = u.strip().lower()
    if not normalized:
        return ""
    return _UNIT_ALIASES.get(normalized, normalized)


def unit_dimension(u: str | None) -> UnitDimension:
    normalized = normalize_unit(u)
    if not normalized:
        return UnitDimension.UNKNOWN
    return _DIMENSION_BY_UNIT.get(normalized, UnitDimension.UNKNOWN)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(UNIT_Q, rounding=ROUND_HALF_UP)


def convert_qty(qty: Decimal, from_unit: str, to_unit: str) -> Decimal:
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    if not source or not target:
        raise UnitConversionError("INCOMPATIBLE_UNITS", f"Cannot convert {from_unit}->{to_unit}")
    if source == target:
        return _quantize(qty)

    source_dim = unit_dimension(source)
    target_dim = unit_dimension(target)
    if source_dim != target_dim:
        raise UnitConversionError("INCOMPATIBLE_UNITS", f"Cannot convert {source}->{target}: incompatible dimensions")

    if source_dim == UnitDimension.VOLUME:
        if source == "l" and target == "ml":
            return _quantize(qty * Decimal("1000"))
        if source == "ml" and target == "l":
            return _quantize(qty / Decimal("1000"))
    elif source_dim == UnitDimension.MASS:
        if source == "kg" and target == "g":
            return _quantize(qty * Decimal("1000"))
        if source == "g" and target == "kg":
            return _quantize(qty / Decimal("1000"))
    elif source_dim == UnitDimension.LENGTH:
        to_mm = {
            "m": Decimal("1000"),
            "cm": Decimal("10"),
            "mm": Decimal("1"),
        }
        if source in to_mm and target in to_mm:
            mm_value = qty * to_mm[source]
            return _quantize(mm_value / to_mm[target])
    elif source_dim == UnitDimension.AREA:
        if source == "m2" and target == "m2":
            return _quantize(qty)
    elif source_dim == UnitDimension.COUNT:
        if source == "pcs" and target == "pcs":
            return _quantize(qty)

    raise UnitConversionError("INCOMPATIBLE_UNITS", f"Cannot convert {source}->{target}")
