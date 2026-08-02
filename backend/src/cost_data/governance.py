"""Shared historical-data governance rules.

The central project record is the source of truth.  Library databases only mirror
published facts and must never invent price meaning or comparability.
"""
from __future__ import annotations

from typing import Any, Literal

from cost_data.models import Project


Comparability = Literal["searchable", "restricted", "benchmark_candidate"]
PRICE_FIELDS = ("tax_inclusion", "price_type", "price_source")
PROFILE_FIELDS = ("structure_form", "area_basis", "above_ground_area", "underground_area")


def price_warnings(context: dict[str, Any]) -> list[str]:
    missing = [field for field in PRICE_FIELDS if not context.get(field)]
    return [f"价格口径待确认：缺少{'、'.join(missing)}" ] if missing else []


def comparability(project: Project) -> Comparability:
    if price_warnings(project.price_context):
        return "restricted"
    if not project.project_type or not all(project.profile.get(field) for field in PROFILE_FIELDS):
        return "restricted"
    return "benchmark_candidate"


def record_warnings(project: Project, *, link_status: str | None = None) -> list[str]:
    warnings = price_warnings(project.price_context)
    if link_status and link_status != "confirmed":
        warnings.append("关联待人工确认，不参与可比统计")
    return warnings
