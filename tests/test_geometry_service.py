from decimal import Decimal

import pytest

from app.services.geometry import GeometryValidationError, compute_room_geometry


def test_geometry_from_length_width_height_with_openings():
    result = compute_room_geometry(length_m=5, width_m=4, ceiling_height_m=2.5, openings_area_m2=3)

    assert result.floor_area_m2 == Decimal("20.00")
    assert result.perimeter_m == Decimal("18.00")
    assert result.wall_area_gross_m2 == Decimal("45.00")
    assert result.wall_area_net_m2 == Decimal("42.00")


def test_geometry_from_floor_perimeter_height():
    result = compute_room_geometry(floor_area_m2=20, perimeter_m=18, ceiling_height_m=2.5, openings_area_m2=0)

    assert result.wall_area_gross_m2 == Decimal("45.00")
    assert result.wall_area_net_m2 == Decimal("45.00")


def test_geometry_without_perimeter_has_warning_and_no_wall_area():
    result = compute_room_geometry(floor_area_m2=20, ceiling_height_m=2.5)

    assert result.floor_area_m2 == Decimal("20.00")
    assert result.wall_area_gross_m2 is None
    assert any("периметра" in warning.lower() for warning in result.warnings)


def test_geometry_openings_more_than_wall_area_clamps_to_zero():
    result = compute_room_geometry(floor_area_m2=20, perimeter_m=18, ceiling_height_m=2.5, openings_area_m2=100)

    assert result.wall_area_gross_m2 == Decimal("45.00")
    assert result.wall_area_net_m2 == Decimal("0.00")
    assert any("проемов" in warning.lower() for warning in result.warnings)


def test_geometry_negative_values_raise_validation_error():
    with pytest.raises(GeometryValidationError):
        compute_room_geometry(floor_area_m2=-1, perimeter_m=18, ceiling_height_m=2.5)
