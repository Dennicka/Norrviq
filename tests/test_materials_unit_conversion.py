from decimal import Decimal

from app.services.unit_conversion import convert_qty


def test_convert_qty_volume_roundtrip():
    qty_ml = convert_qty(Decimal("13.2"), "L", "ml")
    assert qty_ml == Decimal("13200.0000")
