from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


DEFAULT_SCALE = 6
MIN_INT64 = -(2**63)
MAX_INT64 = 2**63 - 1


def _checked_int(value: Decimal) -> int:
    result = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if result < MIN_INT64 or result > MAX_INT64:
        raise OverflowError("定点数超出 64 位整数范围")
    return result


def to_scaled(value: str | Decimal | int | None, scale: int = DEFAULT_SCALE) -> int | None:
    if value is None or value == "":
        return None
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"无效十进制数值: {value}") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"无效十进制数值: {value}")
    factor = Decimal(10) ** scale
    return _checked_int(decimal_value * factor)


def from_scaled(value: int | None, scale: int = DEFAULT_SCALE) -> str | None:
    if value is None:
        return None
    decimal_value = Decimal(value) / (Decimal(10) ** scale)
    text = f"{decimal_value:.{scale}f}".rstrip("0").rstrip(".")
    return text or "0"


def multiply_scaled(
    left: int | None,
    left_scale: int,
    right: int | None,
    right_scale: int,
    result_scale: int = DEFAULT_SCALE,
) -> int | None:
    if left is None or right is None:
        return None
    raw = Decimal(left) * Decimal(right)
    divisor = Decimal(10) ** (left_scale + right_scale - result_scale)
    return _checked_int(raw / divisor)
