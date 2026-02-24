from decimal import Decimal

from app.services.offer_totals import OfferTotalsInput, compute_offer_totals


def test_compute_offer_totals_rounding_discount_and_vat():
    totals = compute_offer_totals(
        OfferTotalsInput(
            labour_subtotal=Decimal("1000.005"),
            materials_subtotal=Decimal("99.994"),
            other_subtotal=Decimal("0"),
            vat_percent=Decimal("25"),
            discount_percent=Decimal("10"),
            discount_amount=Decimal("50"),
            rot_enabled=True,
        )
    )
    assert totals.labour_subtotal == Decimal("1000.01")
    assert totals.materials_subtotal == Decimal("99.99")
    assert totals.discount_amount == Decimal("160.00")
    assert totals.subtotal_ex_vat == Decimal("940.00")
    assert totals.vat_amount == Decimal("235.00")
    assert totals.total_inc_vat == Decimal("1175.00")
    assert totals.rot_base == Decimal("1000.01")
