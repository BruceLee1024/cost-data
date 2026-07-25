from decimal import Decimal

import pytest

from cost_data.fixedpoint import from_scaled, multiply_scaled, to_scaled


def test_fixed_point_round_trip_and_multiplication() -> None:
    assert to_scaled("123.4567894") == 123456789
    assert from_scaled(123456789) == "123.456789"
    assert multiply_scaled(to_scaled("2.5"), 6, to_scaled("4.2"), 6) == to_scaled("10.5")
    assert to_scaled(Decimal("0.0000005")) == 1


def test_fixed_point_rejects_non_finite_and_overflow() -> None:
    with pytest.raises(ValueError):
        to_scaled("NaN")
    with pytest.raises(OverflowError):
        to_scaled("999999999999999999999")
