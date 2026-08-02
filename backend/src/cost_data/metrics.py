from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cost_data.fixedpoint import DEFAULT_SCALE, from_scaled, to_scaled
from cost_data.models import CostItem, Project, ProjectMetric, ProjectVersion, ResourceItem
from cost_data.schemas import DecimalValue, MetricRead
from cost_data.unit_conversion import converted_value


def _divide(numerator: int | None, numerator_scale: int, denominator: int | None, denominator_scale: int) -> int | None:
    if numerator is None or denominator in (None, 0):
        return None
    left = Decimal(numerator) / (Decimal(10) ** numerator_scale)
    right = Decimal(denominator) / (Decimal(10) ** denominator_scale)
    result = (left / right).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return to_scaled(result, DEFAULT_SCALE)


def calculate_metrics(session: Session, version_id: str) -> list[ProjectMetric]:
    version = session.get(ProjectVersion, version_id)
    if not version:
        raise ValueError("项目版本不存在")
    project = session.get(Project, version.project_id)
    if not project:
        raise ValueError("项目不存在")
    session.execute(delete(ProjectMetric).where(ProjectMetric.project_version_id == version_id))
    total_cost = session.scalar(
        select(func.sum(CostItem.total_value)).where(
            CostItem.project_version_id == version_id,
            CostItem.status == "active",
        )
    )
    steel_values = [converted_value(session, item.quantity_value, item.quantity_scale, item.unit, "kg") for item in session.scalars(select(ResourceItem).where(ResourceItem.project_version_id == version_id, ResourceItem.name.like("%钢筋%"))).all()]
    concrete_values = [converted_value(session, item.quantity_value, item.quantity_scale, item.unit, "m3") for item in session.scalars(select(ResourceItem).where(ResourceItem.project_version_id == version_id, (ResourceItem.name.like("%混凝土%") | ResourceItem.name.like("%商品砼%")))).all()]
    steel_quantity = sum(value for value in steel_values if value is not None) or None
    concrete_quantity = sum(value for value in concrete_values if value is not None) or None
    definitions = [
        ("cost_per_area", "单方造价", total_cost, "元/m2", "清单合价合计 ÷ 建筑面积"),
        ("steel_per_area", "钢筋含量", steel_quantity, "kg/m2", "钢筋资源数量合计 ÷ 建筑面积"),
        ("concrete_per_area", "混凝土含量", concrete_quantity, "m3/m2", "混凝土资源数量合计 ÷ 建筑面积"),
    ]
    metrics: list[ProjectMetric] = []
    for code, name, numerator, unit, formula in definitions:
        metric = ProjectMetric(
            project_version_id=version_id,
            code=code,
            name=name,
            value=_divide(numerator, DEFAULT_SCALE, project.area_value, project.area_scale),
            scale=DEFAULT_SCALE,
            unit=unit,
            formula=formula,
            numerator_source={"type": "aggregate", "value": from_scaled(numerator, DEFAULT_SCALE), "excluded_unconvertible": (sum(value is None for value in steel_values) if code == "steel_per_area" else sum(value is None for value in concrete_values) if code == "concrete_per_area" else 0)},
            denominator_source={"type": "project_area", "value": from_scaled(project.area_value, project.area_scale)},
            status="calculated" if project.area_value else "missing_denominator",
        )
        session.add(metric)
        metrics.append(metric)
    session.flush()
    return metrics


def serialize_metric(metric: ProjectMetric) -> MetricRead:
    return MetricRead(
        id=metric.id,
        code=metric.code,
        name=metric.name,
        value=DecimalValue(value=from_scaled(metric.value, metric.scale), scale=metric.scale, unit=metric.unit),
        formula=metric.formula,
        numerator_source=metric.numerator_source,
        denominator_source=metric.denominator_source,
        status=metric.status,
    )
