from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from cost_data.config import get_settings
from cost_data.models import ImportIssue
from cost_data.search import get_cost_item


HEADER_FILL = PatternFill("solid", fgColor="173F35")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _style_header(sheet) -> None:  # type: ignore[no-untyped-def]
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"


def export_reference_prices(session: Session, item_ids: list[str]) -> Path:
    workbook = Workbook(write_only=False)
    sheet = workbook.active
    sheet.title = "参考价分析"
    sheet.append(
        [
            "清单编码",
            "清单名称",
            "项目特征",
            "规格",
            "单位",
            "综合单价",
            "项目名称",
            "地区",
            "计价时间",
            "专业",
            "计价体系",
            "原始文件",
            "工作表",
            "来源行",
        ]
    )
    _style_header(sheet)
    for item_id in item_ids:
        item = get_cost_item(session, item_id)
        if not item:
            continue
        sheet.append(
            [
                item.code,
                item.name,
                item.description,
                item.specification,
                item.unit,
                item.unit_price.value,
                item.project_name,
                item.region,
                item.pricing_date,
                item.specialty,
                item.pricing_mode,
                item.source.file_name,
                item.source.sheet_name,
                item.source.start_row,
            ]
        )
    widths = [16, 32, 42, 24, 10, 16, 28, 12, 14, 14, 16, 28, 22, 10]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    path = get_settings().export_dir / "参考价分析.xlsx"
    workbook.save(path)
    return path


def export_quality_report(session: Session, job_id: str) -> Path:
    workbook = Workbook(write_only=False)
    sheet = workbook.active
    sheet.title = "导入质量报告"
    sheet.append(["严重程度", "问题代码", "问题说明", "工作表", "位置", "状态", "建议处理"])
    _style_header(sheet)
    issues = session.scalars(
        select(ImportIssue).where(ImportIssue.import_job_id == job_id).order_by(ImportIssue.severity, ImportIssue.created_at)
    ).all()
    for issue in issues:
        sheet.append(
            [
                issue.severity,
                issue.code,
                issue.message,
                issue.sheet_name,
                issue.cell_range,
                issue.status,
                issue.suggested_action,
            ]
        )
    widths = [12, 24, 60, 24, 14, 12, 50]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    path = get_settings().export_dir / f"导入质量报告-{job_id[:8]}.xlsx"
    workbook.save(path)
    return path

