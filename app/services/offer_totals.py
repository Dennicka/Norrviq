from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")


@dataclass
class OfferTotalsInput:
    labour_subtotal: Decimal
    materials_subtotal: Decimal
    other_subtotal: Decimal
    vat_percent: Decimal
    discount_amount: Decimal = Decimal("0")
    discount_percent: Decimal = Decimal("0")
    rot_enabled: bool = False


@dataclass
class OfferTotals:
    labour_subtotal: Decimal
    materials_subtotal: Decimal
    other_subtotal: Decimal
    discount_amount: Decimal
    subtotal_ex_vat: Decimal
    vat_amount: Decimal
    total_inc_vat: Decimal
    rot_base: Decimal


def q(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def compute_offer_totals(payload: OfferTotalsInput) -> OfferTotals:
    """
    SEK rounding policy:
    1) All monetary components are rounded to öre before rollups.
    2) Percentage discount is applied on subtotal before VAT, then rounded to öre.
    3) VAT is calculated on discounted subtotal, then rounded to öre.
    """

    labour = q(payload.labour_subtotal)
    materials = q(payload.materials_subtotal)
    other = q(payload.other_subtotal)
    gross_subtotal = q(labour + materials + other)

    percent_discount = Decimal("0")
    if payload.discount_percent and payload.discount_percent > 0:
        percent_discount = q(gross_subtotal * Decimal(str(payload.discount_percent)) / Decimal("100"))

    fixed_discount = q(payload.discount_amount)
    discount = q(percent_discount + fixed_discount)
    if discount > gross_subtotal:
        discount = gross_subtotal

    subtotal = q(gross_subtotal - discount)
    vat = q(subtotal * Decimal(str(payload.vat_percent)) / Decimal("100"))
    total = q(subtotal + vat)

    rot_base = labour if payload.rot_enabled else Decimal("0.00")
    return OfferTotals(
        labour_subtotal=labour,
        materials_subtotal=materials,
        other_subtotal=other,
        discount_amount=discount,
        subtotal_ex_vat=subtotal,
        vat_amount=vat,
        total_inc_vat=total,
        rot_base=q(rot_base),
    )
