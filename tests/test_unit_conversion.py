from decimal import Decimal

import pytest

from app.services.unit_conversion import UnitConversionError, convert_qty


def test_volume_l_to_ml():
    assert convert_qty(Decimal("1.5"), "l", "ml") == Decimal("1500.0000")


def test_mass_kg_to_g():
    assert convert_qty(Decimal("2"), "kg", "g") == Decimal("2000.0000")


def test_length_m_to_cm():
    assert convert_qty(Decimal("1.2"), "m", "cm") == Decimal("120.0000")


def test_incompatible_units_raises():
    with pytest.raises(UnitConversionError) as exc_info:
        convert_qty(Decimal("1"), "l", "kg")

    assert exc_info.value.code == "INCOMPATIBLE_UNITS"
