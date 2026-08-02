from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from cost_data.fixedpoint import from_scaled
from cost_data.models import CostItem, FeeRate, MeasureItem, Project, ProjectMetric, ProjectVersion, QuotaItem, ResourceItem, SourceFile
from cost_data.schemas import DecimalValue, SearchIntent, SourceRef, WorkspaceRecord, WorkspaceSearchResult
from cost_data.search import decimal_value
from cost_data.governance import comparability as governance_comparability, record_warnings


def _comparable(project: Project) -> str:
    return governance_comparability(project)


def _source(source: SourceFile | None, sheet: str, row: int) -> SourceRef | None:
    if not source:
        return None
    return SourceRef(file_id=source.id, file_name=source.original_name, sheet_name=sheet, start_row=row, cell_range=str(row))


def _allowed(project: Project, intent: SearchIntent, name: str, unit: str | None) -> bool:
    if intent.region and project.region != intent.region: return False
    if intent.specialty and project.specialty != intent.specialty: return False
    if intent.project_type and project.project_type != intent.project_type: return False
    if intent.pricing_mode and project.pricing_mode != intent.pricing_mode: return False
    if intent.result_stage and project.result_stage != intent.result_stage: return False
    if intent.pricing_date_from and project.pricing_date < intent.pricing_date_from: return False
    if intent.pricing_date_to and project.pricing_date > intent.pricing_date_to: return False
    if intent.unit and unit != intent.unit: return False
    if intent.query and intent.query.lower() not in name.lower(): return False
    if intent.data_status == "restricted" and _comparable(project) != "restricted": return False
    return True


def _record(item, project: Project, version: ProjectVersion, source: SourceFile | None, data_type: str, *, quantity=None, price=None, total=None, unit=None, code=None, specification=None, attributes=None) -> WorkspaceRecord:
    return WorkspaceRecord(id=item.id, data_type=data_type, name=item.name, code=code if code is not None else getattr(item, "code", None), specification=specification if specification is not None else getattr(item, "specification", None), unit=unit if unit is not None else getattr(item, "unit", None), quantity=quantity or DecimalValue(value=None), unit_price=price or DecimalValue(value=None, currency="CNY"), total=total or DecimalValue(value=None, currency="CNY"), project_id=project.id, project_name=project.name, project_version_id=version.id, region=project.region, pricing_date=project.pricing_date, specialty=project.specialty, pricing_mode=project.pricing_mode, result_stage=project.result_stage, comparability=_comparable(project), data_status="published", price_context=project.price_context, warnings=record_warnings(project), source=_source(source, getattr(item, "sheet_name", "项目指标"), getattr(item, "source_row", 0)), attributes=attributes or {})


def search_workspace(session: Session, intent: SearchIntent) -> WorkspaceSearchResult:
    types = {intent.data_type} if intent.data_type != "all" else {"bill", "quota", "resource", "measure", "fee_rate", "metric"}
    records: list[WorkspaceRecord] = []
    versions = session.execute(select(ProjectVersion, Project).join(Project).where(ProjectVersion.status == "published")).all()
    for version, project in versions:
        if "bill" in types:
            for item, source in session.execute(select(CostItem, SourceFile).join(SourceFile).where(CostItem.project_version_id == version.id, CostItem.status == "active")).all():
                if _allowed(project, intent, " ".join(filter(None, [item.name, item.code, item.description, item.specification])), item.unit): records.append(_record(item, project, version, source, "bill", quantity=decimal_value(item.quantity_value, item.quantity_scale, unit=item.unit), price=decimal_value(item.unit_price_value, item.unit_price_scale, currency=item.currency), total=decimal_value(item.total_value, item.total_scale, currency=item.currency), attributes=item.import_attributes))
        if "resource" in types:
            for item, source in session.execute(select(ResourceItem, SourceFile).join(SourceFile).where(ResourceItem.project_version_id == version.id)).all():
                if (not intent.resource_kind or item.kind == intent.resource_kind) and _allowed(project, intent, " ".join(filter(None, [item.name, item.code, item.specification])), item.unit): records.append(_record(item, project, version, source, "resource", quantity=decimal_value(item.quantity_value, item.quantity_scale, unit=item.unit), price=decimal_value(item.price_value, item.price_scale, currency="CNY"), total=decimal_value(item.amount_value, item.amount_scale, currency="CNY"), attributes={"kind": item.kind}))
        if "measure" in types:
            for item, source in session.execute(select(MeasureItem, SourceFile).join(SourceFile).where(MeasureItem.project_version_id == version.id)).all():
                if _allowed(project, intent, item.name, None): records.append(_record(item, project, version, source, "measure", total=decimal_value(item.amount_value, item.amount_scale, currency="CNY")))
        if "fee_rate" in types:
            for item, source in session.execute(select(FeeRate, SourceFile).join(SourceFile).where(FeeRate.project_version_id == version.id)).all():
                if _allowed(project, intent, " ".join(filter(None, [item.name, item.basis])), "%"): records.append(_record(item, project, version, source, "fee_rate", unit="%", price=decimal_value(item.rate_value, item.rate_scale, unit="%"), attributes={"basis": item.basis or ""}))
        if "quota" in types:
            quota_query = (
                select(QuotaItem, SourceFile, CostItem)
                .select_from(QuotaItem)
                .join(CostItem, CostItem.id == QuotaItem.cost_item_id)
                .join(SourceFile, SourceFile.id == QuotaItem.source_file_id)
                .where(CostItem.project_version_id == version.id)
            )
            for item, source, cost in session.execute(quota_query).all():
                if _allowed(project, intent, " ".join(filter(None, [item.name, item.code])), item.unit): records.append(_record(item, project, version, source, "quota", quantity=decimal_value(item.consumption_value, item.consumption_scale, unit=item.unit)))
        if "metric" in types:
            for item in session.scalars(select(ProjectMetric).where(ProjectMetric.project_version_id == version.id)).all():
                if _allowed(project, intent, item.name, item.unit): records.append(_record(item, project, version, None, "metric", unit=item.unit, total=decimal_value(item.value, item.scale, unit=item.unit), attributes={"formula": item.formula, "status": item.status, "numerator_source": item.numerator_source, "denominator_source": item.denominator_source}))
    records.sort(key=lambda record: (record.pricing_date, record.project_name, record.name), reverse=True)
    return WorkspaceSearchResult(items=records[:intent.limit], total=len(records))
