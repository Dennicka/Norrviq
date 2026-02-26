from decimal import Decimal

from app.services.materials_bom import _convert_qty


def test_pack_conversion_rounds_to_packs():
    qty_packs = _convert_qty(Decimal("13.2"), "L", "PACK", pack_size=Decimal("10"), pack_unit="L")
    assert qty_packs == Decimal("1.32")
