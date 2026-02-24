from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANTUM = Decimal("0.01")
QTY_QUANTUM = Decimal("0.001")


def to_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def round_money_sek(value: object) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def round_quantity(value: object) -> Decimal:
    return to_decimal(value).quantize(QTY_QUANTUM, rounding=ROUND_HALF_UP)


def money_eq(left: object, right: object, tolerance: Decimal = MONEY_QUANTUM) -> bool:
    return abs(to_decimal(left) - to_decimal(right)) <= tolerance
