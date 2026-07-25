from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from cost_data.models import NormalizationRule


UNIT_ALIASES = {
    "㎡": "m2",
    "m²": "m2",
    "平方米": "m2",
    "立方米": "m3",
    "m³": "m3",
    "吨": "t",
    "千克": "kg",
    "公斤": "kg",
    "延米": "m",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"[\s·•,，;；:：()（）\[\]【】]+", " ", text)
    return text.strip()


def normalize_unit(value: str | None, session: Session | None = None) -> str:
    raw = normalize_text(value).replace(" ", "")
    if not raw:
        return ""
    if session is not None:
        rule = session.scalar(
            select(NormalizationRule).where(
                NormalizationRule.rule_type == "unit",
                NormalizationRule.enabled.is_(True),
                NormalizationRule.source_value == raw,
            )
        )
        if rule:
            return rule.target_value
    return UNIT_ALIASES.get(raw, raw)


def apply_synonyms(value: str, session: Session) -> str:
    result = normalize_text(value)
    rules = session.scalars(
        select(NormalizationRule).where(
            NormalizationRule.rule_type == "synonym",
            NormalizationRule.enabled.is_(True),
        )
    ).all()
    for rule in rules:
        result = result.replace(normalize_text(rule.source_value), normalize_text(rule.target_value))
    return result


def specification_tokens(value: str | None) -> set[str]:
    normalized = normalize_text(value)
    return {token for token in re.findall(r"[a-z]+\d+(?:\.\d+)?|\d+(?:\.\d+)?|[\u4e00-\u9fff]{2,}", normalized) if token}

