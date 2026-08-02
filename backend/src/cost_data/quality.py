from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cost_data.fixedpoint import from_scaled
from cost_data.models import CostItem, ImportIssue, ImportJob, Project, ProjectVersion, ResourceItem, SourceFile
from cost_data.schemas import QualityIssueRead, QualityReportRead, SourceRef
from cost_data.governance import price_warnings


PROFILE_FIELDS = ("structure_form", "area_basis", "above_ground_area", "underground_area")


def source_for(session: Session, source_file_id: str, sheet_name: str, row: int) -> SourceRef | None:
    source = session.get(SourceFile, source_file_id)
    if not source:
        return None
    return SourceRef(file_id=source.id, file_name=source.original_name, sheet_name=sheet_name, start_row=row, cell_range=str(row))


def build_quality_report(session: Session, version_id: str) -> QualityReportRead:
    version = session.get(ProjectVersion, version_id)
    if not version:
        raise ValueError("项目版本不存在")
    project = session.get(Project, version.project_id)
    if not project:
        raise ValueError("项目不存在")
    issues: list[QualityIssueRead] = []
    for issue in session.scalars(select(ImportIssue).join(ImportJob).where(ImportJob.project_version_id == version_id, ImportIssue.status == "open")).all():
        issues.append(QualityIssueRead(severity="error" if issue.severity == "error" else "warning", code=issue.code, message=issue.message, project_version_id=version_id, source=source_for(session, issue.source_file_id, issue.sheet_name or "", 0) if issue.source_file_id else None))
    missing = [field for field in PROFILE_FIELDS if not project.profile.get(field)]
    if not project.project_type:
        missing.insert(0, "project_type")
    if missing:
        issues.append(QualityIssueRead(severity="warning", code="PROFILE_INCOMPLETE", message=f"项目画像尚缺：{'、'.join(missing)}；可检索但不进入标杆样本池", project_version_id=version_id))
    for warning in price_warnings(project.price_context):
        issues.append(QualityIssueRead(severity="warning", code="PRICE_CONTEXT_INCOMPLETE", message=f"{warning}；只展示原始价，不参与可比统计", project_version_id=version_id))
    for resource in session.scalars(select(ResourceItem).where(ResourceItem.project_version_id == version_id, ResourceItem.name.like("%钢筋%"))).all():
        if resource.unit not in {"kg", "t", "吨"}:
            issues.append(QualityIssueRead(severity="warning", code="STEEL_UNIT_UNCONFIRMED", message=f"钢筋“{resource.name}”单位“{resource.unit or '空'}”无法换算为 kg", project_version_id=version_id, source=source_for(session, resource.source_file_id, resource.sheet_name, resource.source_row)))
    for item in session.scalars(select(CostItem).where(CostItem.project_version_id == version_id, CostItem.quantity_value.is_not(None), CostItem.unit_price_value.is_not(None), CostItem.total_value.is_not(None))).all():
        quantity = Decimal(from_scaled(item.quantity_value, item.quantity_scale) or "0")
        price = Decimal(from_scaled(item.unit_price_value, item.unit_price_scale) or "0")
        total = Decimal(from_scaled(item.total_value, item.total_scale) or "0")
        if abs(quantity * price - total) > Decimal("0.02"):
            issues.append(QualityIssueRead(severity="warning", code="AMOUNT_UNBALANCED", message=f"{item.name} 的工程量乘综合单价与合价不一致", project_version_id=version_id, source=source_for(session, item.source_file_id, item.sheet_name, item.source_row)))
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = len(issues) - errors
    return QualityReportRead(project_version_id=version_id, publishable=errors == 0, summary={"errors": errors, "warnings": warnings, "total": len(issues)}, issues=issues)
