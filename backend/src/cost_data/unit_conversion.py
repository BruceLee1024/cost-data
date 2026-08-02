from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cost_data.fixedpoint import DEFAULT_SCALE, from_scaled, to_scaled
from cost_data.models import UnitConversion
from cost_data.normalization import normalize_unit


BUILT_INS = {("t", "kg"): Decimal("1000"), ("吨", "kg"): Decimal("1000"), ("100m3", "m3"): Decimal("100")}


def conversion_factor(session: Session, source_unit: str | None, target_unit: str) -> Decimal | None:
    source = normalize_unit(source_unit)
    target = normalize_unit(target_unit)
    if source == target:
        return Decimal("1")
    factor = BUILT_INS.get((source or "", target or ""))
    if factor is not None:
        return factor
    rule = session.scalar(select(UnitConversion).where(UnitConversion.source_unit == source, UnitConversion.target_unit == target, UnitConversion.enabled.is_(True)))
    return Decimal(from_scaled(rule.factor_value, rule.factor_scale)) if rule else None


def converted_value(session: Session, value: int | None, scale: int, source_unit: str | None, target_unit: str) -> int | None:
    factor = conversion_factor(session, source_unit, target_unit)
    if value is None or factor is None:
        return None
    return to_scaled(Decimal(from_scaled(value, scale) or "0") * factor, DEFAULT_SCALE)
