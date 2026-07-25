from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cost_data.config import get_settings
from cost_data.db import SessionLocal
from cost_data.fixedpoint import to_scaled
from cost_data.models import (
    CostItem,
    FeeRate,
    ImportIssue,
    ImportJob,
    MeasureItem,
    ProjectVersion,
    QuotaItem,
    RateComponent,
    ResourceItem,
    SourceFile,
)
from cost_data.normalization import normalize_text, normalize_unit


HEADER_ALIASES = {
    "code": {"清单编码", "项目编码", "编码", "定额编号", "材料编码"},
    "name": {"项目名称", "清单名称", "名称", "材料名称", "费用名称", "定额名称"},
    "description": {"项目特征", "项目特征描述", "工作内容", "描述"},
    "specification": {"规格型号", "规格", "型号", "特征"},
    "unit": {"计量单位", "单位"},
    "quantity": {"工程量", "数量", "消耗量", "含量"},
    "unit_price": {"综合单价", "市场价", "单价", "除税单价"},
    "total": {"合价", "综合合价", "金额", "费用"},
    "category": {"费用类别", "类别", "构成", "费用构成"},
    "basis": {"取费基础", "计算基础", "取费基数"},
    "rate": {"费率", "取费费率"},
}


@dataclass
class ParsedTable:
    report_type: str
    sheet_name: str
    header_row: int
    columns: dict[str, int]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_file(source: Path, original_name: str) -> tuple[str, str, int]:
    settings = get_settings()
    digest = file_sha256(source)
    suffix = Path(original_name).suffix.lower()
    relative = Path(digest[:2]) / f"{digest}{suffix}"
    destination = settings.raw_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return digest, str(relative), destination.stat().st_size


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _find_columns(row: tuple[Cell, ...]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, cell in enumerate(row, start=1):
        value = normalize_text(_cell_text(cell.value)).replace(" ", "")
        if not value:
            continue
        for field, aliases in HEADER_ALIASES.items():
            if value in {normalize_text(alias).replace(" ", "") for alias in aliases}:
                columns.setdefault(field, index)
    return columns


def _classify(sheet_name: str, columns: dict[str, int]) -> str:
    name = normalize_text(sheet_name)
    if "综合单价分析" in name or ("category" in columns and "code" in columns and "total" in columns):
        return "rate_analysis"
    if "工料机" in name or "材料" in name or "人工" in name or "机械" in name:
        return "resource"
    if "措施" in name:
        return "measure"
    if "取费" in name or "费率" in name or "rate" in columns:
        return "fee_rate"
    if "定额" in name and "quantity" in columns:
        return "quota"
    if "name" in columns and ("unit_price" in columns or "total" in columns):
        return "bill"
    return "unknown"


def inspect_workbook(path: Path) -> tuple[list[str], list[ParsedTable]]:
    workbook = load_workbook(path, read_only=False, data_only=False, keep_links=False)
    tables: list[ParsedTable] = []
    sheet_names = list(workbook.sheetnames)
    try:
        for worksheet in workbook.worksheets:
            for row_no, row in enumerate(worksheet.iter_rows(min_row=1, max_row=min(25, worksheet.max_row)), start=1):
                columns = _find_columns(row)
                if "name" in columns and len(columns) >= 2:
                    tables.append(
                        ParsedTable(
                            report_type=_classify(worksheet.title, columns),
                            sheet_name=worksheet.title,
                            header_row=row_no,
                            columns=columns,
                        )
                    )
                    break
    finally:
        workbook.close()
    return sheet_names, tables


def _value(row: tuple[Any, ...], columns: dict[str, int], key: str) -> Any:
    index = columns.get(key)
    return row[index - 1] if index and index <= len(row) else None


def _issue(
    session: Session,
    job_id: str,
    source_file_id: str | None,
    severity: str,
    code: str,
    message: str,
    sheet_name: str | None = None,
    cell_range: str | None = None,
    action: str | None = None,
) -> None:
    session.add(
        ImportIssue(
            import_job_id=job_id,
            source_file_id=source_file_id,
            severity=severity,
            code=code,
            message=message,
            sheet_name=sheet_name,
            cell_range=cell_range,
            suggested_action=action,
        )
    )


def _safe_scaled(value: Any, *, issue_context: tuple[Session, str, str, str, int], field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return to_scaled(str(value))
    except ValueError:
        session, job_id, source_id, sheet, row_no = issue_context
        _issue(
            session,
            job_id,
            source_id,
            "warning",
            "INVALID_DECIMAL",
            f"{field} 无法解析为数值：{value}",
            sheet,
            str(row_no),
            "核对原始单元格或将该问题标记为忽略",
        )
        return None


def _parse_table(
    session: Session,
    job: ImportJob,
    source_file: SourceFile,
    path: Path,
    table: ParsedTable,
    pending_analysis: list[dict[str, Any]],
) -> int:
    values_book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    formula_book = load_workbook(path, read_only=False, data_only=False, keep_links=False)
    count = 0
    try:
        values_sheet = values_book[table.sheet_name]
        formula_sheet = formula_book[table.sheet_name]
        for row_no, row in enumerate(
            values_sheet.iter_rows(min_row=table.header_row + 1, values_only=True),
            start=table.header_row + 1,
        ):
            name = _cell_text(_value(row, table.columns, "name"))
            code = _cell_text(_value(row, table.columns, "code")) or None
            if not name and not code:
                continue
            if name in {"合计", "小计", "总计"} or name.endswith("合计"):
                continue
            context = (session, job.id, source_file.id, table.sheet_name, row_no)
            unit = normalize_unit(_cell_text(_value(row, table.columns, "unit")), session) or None
            quantity = _safe_scaled(_value(row, table.columns, "quantity"), issue_context=context, field="工程量")
            unit_price = _safe_scaled(_value(row, table.columns, "unit_price"), issue_context=context, field="单价")
            total = _safe_scaled(_value(row, table.columns, "total"), issue_context=context, field="金额")

            for numeric_field in ("quantity", "unit_price", "total", "rate"):
                col = table.columns.get(numeric_field)
                if col:
                    formula_cell = formula_sheet.cell(row=row_no, column=col)
                    cached = _value(row, table.columns, numeric_field)
                    if isinstance(formula_cell.value, str) and formula_cell.value.startswith("=") and cached is None:
                        _issue(
                            session,
                            job.id,
                            source_file.id,
                            "warning",
                            "FORMULA_CACHE_MISSING",
                            f"公式单元格 {formula_cell.coordinate} 没有缓存结果",
                            table.sheet_name,
                            formula_cell.coordinate,
                            "使用 Excel 打开并重新保存后再次导入",
                        )

            if table.report_type == "bill":
                item = CostItem(
                    project_version_id=job.project_version_id,
                    source_file_id=source_file.id,
                    code=code,
                    name=name,
                    normalized_name=normalize_text(name),
                    description=_cell_text(_value(row, table.columns, "description")) or None,
                    specification=_cell_text(_value(row, table.columns, "specification")) or None,
                    unit=unit,
                    quantity_value=quantity,
                    unit_price_value=unit_price,
                    total_value=total,
                    sheet_name=table.sheet_name,
                    source_row=row_no,
                )
                session.add(item)
            elif table.report_type == "resource":
                lower_name = name.lower()
                kind = "labor" if "人工" in lower_name else "machine" if "机械" in lower_name else "material"
                session.add(
                    ResourceItem(
                        project_version_id=job.project_version_id,
                        source_file_id=source_file.id,
                        kind=kind,
                        code=code,
                        name=name,
                        specification=_cell_text(_value(row, table.columns, "specification")) or None,
                        unit=unit,
                        quantity_value=quantity,
                        price_value=unit_price,
                        amount_value=total,
                        sheet_name=table.sheet_name,
                        source_row=row_no,
                    )
                )
            elif table.report_type == "measure":
                session.add(
                    MeasureItem(
                        project_version_id=job.project_version_id,
                        source_file_id=source_file.id,
                        name=name,
                        amount_value=total if total is not None else unit_price,
                        sheet_name=table.sheet_name,
                        source_row=row_no,
                    )
                )
            elif table.report_type == "fee_rate":
                session.add(
                    FeeRate(
                        project_version_id=job.project_version_id,
                        source_file_id=source_file.id,
                        name=name,
                        rate_value=_safe_scaled(_value(row, table.columns, "rate"), issue_context=context, field="费率"),
                        basis=_cell_text(_value(row, table.columns, "basis")) or None,
                        sheet_name=table.sheet_name,
                        source_row=row_no,
                    )
                )
            elif table.report_type in {"rate_analysis", "quota"}:
                pending_analysis.append(
                    {
                        "type": table.report_type,
                        "source_file_id": source_file.id,
                        "sheet_name": table.sheet_name,
                        "source_row": row_no,
                        "code": code,
                        "name": name,
                        "category": _cell_text(_value(row, table.columns, "category")) or "其他",
                        "unit": unit,
                        "quantity": quantity,
                        "amount": total if total is not None else unit_price,
                    }
                )
            count += 1
    finally:
        values_book.close()
        formula_book.close()
    return count


def _link_analysis(session: Session, job: ImportJob, rows: list[dict[str, Any]]) -> None:
    session.flush()
    for row in rows:
        if not row["code"]:
            _issue(
                session,
                job.id,
                row["source_file_id"],
                "warning",
                "ANALYSIS_CODE_MISSING",
                f"{row['name']} 缺少关联清单编码",
                row["sheet_name"],
                str(row["source_row"]),
            )
            continue
        item = session.scalar(
            select(CostItem).where(
                CostItem.project_version_id == job.project_version_id,
                CostItem.code == row["code"],
            )
        )
        if not item:
            _issue(
                session,
                job.id,
                row["source_file_id"],
                "warning",
                "ANALYSIS_LINK_FAILED",
                f"未找到编码 {row['code']} 对应的清单项",
                row["sheet_name"],
                str(row["source_row"]),
                "确认编码或在异常复核中忽略",
            )
            continue
        if row["type"] == "quota":
            session.add(
                QuotaItem(
                    cost_item_id=item.id,
                    code=row["code"],
                    name=row["name"],
                    unit=row["unit"],
                    consumption_value=row["quantity"],
                    source_file_id=row["source_file_id"],
                    sheet_name=row["sheet_name"],
                    source_row=row["source_row"],
                )
            )
        else:
            session.add(
                RateComponent(
                    cost_item_id=item.id,
                    category=row["category"],
                    name=row["name"],
                    value=row["amount"],
                    source_file_id=row["source_file_id"],
                    sheet_name=row["sheet_name"],
                    source_row=row["source_row"],
                )
            )


def process_import_job(job_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as session:
        job = session.get(ImportJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        session.commit()
        pending_analysis: list[dict[str, Any]] = []
        try:
            files = session.scalars(
                select(SourceFile).where(SourceFile.import_job_id == job.id).order_by(SourceFile.original_name)
            ).all()
            for position, source_file in enumerate(files, start=1):
                path = settings.raw_dir / source_file.relative_path
                try:
                    sheet_names, tables = inspect_workbook(path)
                    source_file.sheet_names = sheet_names
                    known_tables = [table for table in tables if table.report_type != "unknown"]
                    source_file.report_type = known_tables[0].report_type if known_tables else "unknown"
                    if not known_tables:
                        _issue(
                            session,
                            job.id,
                            source_file.id,
                            "warning",
                            "REPORT_UNRECOGNIZED",
                            "未识别到受支持的报表表头",
                            action="核对文件是否为清单、综合单价分析、工料机或措施项目表",
                        )
                    for table in known_tables:
                        _parse_table(session, job, source_file, path, table, pending_analysis)
                except Exception as exc:
                    _issue(
                        session,
                        job.id,
                        source_file.id,
                        "error",
                        "WORKBOOK_READ_FAILED",
                        f"工作簿读取失败：{exc}",
                        action="确认文件未损坏且格式为 xlsx 或 xlsm",
                    )
                job.processed_files = position
                job.progress = int(position / max(len(files), 1) * 85)
                session.commit()
            _link_analysis(session, job, pending_analysis)
            item_count = session.scalar(
                select(func.count(CostItem.id)).where(CostItem.project_version_id == job.project_version_id)
            ) or 0
            if item_count == 0:
                _issue(
                    session,
                    job.id,
                    None,
                    "error",
                    "NO_COST_ITEMS",
                    "本次导入没有提取到任何清单项",
                    action="检查清单表表头或更换导入文件",
                )
            job.status = "review"
            job.progress = 100
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
        except Exception as exc:
            session.rollback()
            job = session.get(ImportJob, job_id)
            if job:
                job.status = "failed"
                job.error_summary = str(exc)
                job.finished_at = datetime.now(timezone.utc)
                session.commit()


def next_version_no(session: Session, project_id: str) -> int:
    current = session.scalar(
        select(func.max(ProjectVersion.version_no)).where(ProjectVersion.project_id == project_id)
    )
    return (current or 0) + 1
