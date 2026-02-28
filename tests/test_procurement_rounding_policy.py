from decimal import Decimal

from app.services.procurement_rounding import ProcurementRoundingPolicy, compute_packs_needed


def test_compute_packs_needed_ceil_default():
    packs = compute_packs_needed(Decimal("2.0"), Decimal("10.0"), ProcurementRoundingPolicy())

    assert packs == Decimal("1")


def test_compute_packs_needed_floor():
    policy = ProcurementRoundingPolicy(rounding_mode="FLOOR")
    packs = compute_packs_needed(Decimal("12.0"), Decimal("10.0"), policy)

    assert packs == Decimal("1")


def test_compute_packs_needed_nearest_halves_up():
    policy = ProcurementRoundingPolicy(rounding_mode="NEAREST")
    packs = compute_packs_needed(Decimal("15.0"), Decimal("10.0"), policy)

    assert packs == Decimal("2")


def test_min_packs_and_multiple():
    policy = ProcurementRoundingPolicy(min_packs=2, pack_multiple=2)

    low = compute_packs_needed(Decimal("1.0"), Decimal("10.0"), policy)
    high = compute_packs_needed(Decimal("21.0"), Decimal("10.0"), policy)

    assert low == Decimal("2")
    assert high == Decimal("4")
