from __future__ import annotations

import json
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from cost_data import __version__
from cost_data.ai import (
    get_ai_configuration,
    get_api_key,
    parse_search_intent,
    review_candidates,
    redact_payload,
    set_ai_configuration,
    set_api_key,
    suggest_import_mapping,
)
from cost_data.backups import create_backup, stage_restore, validate_backup
from cost_data.config import get_settings
from cost_data.db import get_db, rebuild_fts
from cost_data.exports import export_quality_report, export_reference_prices
from cost_data.fixedpoint import from_scaled, to_scaled
from cost_data.importer import archive_file, next_version_no, process_import_job, save_parser_profiles
from cost_data.metrics import calculate_metrics, serialize_metric
from cost_data.models import (
    AICall,
    AIConsent,
    AppSetting,
    AuditEvent,
    CostItem,
    ImportIssue,
    ImportJob,
    MatchDecision,
    MatchSession,
    MetricTemplate,
    NormalizationRule,
    Project,
    ProjectMetric,
    ProjectVersion,
    SourceFile,
    UnitConversion,
)
from cost_data.schemas import (
    AIConsentUpdate,
    AICallRead,
    AIPreviewRead,
    AIPreviewRequest,
    AISuggestion,
    AISettingsRead,
    AISettingsUpdate,
    BackupCreate,
    BackupRead,
    BenchmarkRead,
    ComparisonRead,
    ComparisonRequest,
    DecimalValue,
    HealthRead,
    ImportIssueRead,
    ImportMappingSuggestion,
    ImportMappingConfirmation,
    ImportParsePreview,
    ImportRead,
    IssueResolve,
    MatchDecisionCreate,
    CandidateReviewRequest,
    MatchSessionCreate,
    MatchSessionRead,
    NaturalLanguageQuery,
    NormalizationRuleCreate,
    NormalizationRuleRead,
    ProjectCreate,
    ProjectDetail,
    ProjectProfileUpdate,
    ProjectSummary,
    ProjectVersionRead,
    RestoreCreate,
    RuleUpdate,
    SearchIntent,
    SearchResult,
    SourceRef,
    UnitConversionCreate,
    UnitConversionRead,
    UnitConversionUpdate,
    MetricTemplateCreate,
    MetricTemplateRead,
    QualityReportRead,
    LibraryRecordRead,
    BillRecordUpdate,
    LibrarySummary,
    WorkspaceRecord,
    WorkspaceSearchResult,
)
from cost_data.search import compare_cost_items, search_cost_items, serialize_match_session
from cost_data.quality import build_quality_report
from cost_data.unit_conversion import conversion_factor
from cost_data.workspace import search_workspace
from cost_data.libraries import LIBRARIES, get_record as get_library_record, search as search_library, summaries as library_summaries, sync_version
from cost_data.governance import comparability as governance_comparability, record_warnings


router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]


def _serialize_project(session: Session, project: Project) -> ProjectSummary:
    latest = session.scalar(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project.id)
        .order_by(desc(ProjectVersion.version_no))
        .limit(1)
    )
    item_count = 0
    issue_count = 0
    if latest:
        item_count = session.scalar(
            select(func.count(CostItem.id)).where(CostItem.project_version_id == latest.id)
        ) or 0
        issue_count = session.scalar(
            select(func.count(ImportIssue.id))
            .join(ImportJob, ImportJob.id == ImportIssue.import_job_id)
            .where(ImportJob.project_version_id == latest.id, ImportIssue.status == "open")
        ) or 0
    return ProjectSummary(
        id=project.id,
        name=project.name,
        region=project.region,
        pricing_date=project.pricing_date,
        specialty=project.specialty,
        pricing_mode=project.pricing_mode,
        result_stage=project.result_stage,
        project_type=project.project_type,
        profile=project.profile,
        price_context=project.price_context,
        comparability=governance_comparability(project),
        area=DecimalValue(value=from_scaled(project.area_value, project.area_scale), scale=project.area_scale, unit=project.area_unit),
        latest_version_id=latest.id if latest else None,
        latest_version_no=latest.version_no if latest else None,
        latest_status=latest.status if latest else None,
        item_count=item_count,
        issue_count=issue_count,
        created_at=project.created_at,
    )


def _serialize_version(session: Session, version: ProjectVersion) -> ProjectVersionRead:
    return ProjectVersionRead(
        id=version.id,
        project_id=version.project_id,
        version_no=version.version_no,
        status=version.status,
        label=version.label,
        published_at=version.published_at,
        created_at=version.created_at,
        file_count=session.scalar(select(func.count(SourceFile.id)).where(SourceFile.project_version_id == version.id)) or 0,
        item_count=session.scalar(select(func.count(CostItem.id)).where(CostItem.project_version_id == version.id)) or 0,
    )


def _serialize_import(session: Session, job: ImportJob) -> ImportRead:
    return ImportRead(
        id=job.id,
        project_id=job.project_id,
        project_version_id=job.project_version_id,
        status=job.status,
        progress=job.progress,
        total_files=job.total_files,
        processed_files=job.processed_files,
        error_summary=job.error_summary,
        parse_preview_available=bool(job.parse_preview),
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        open_issue_count=session.scalar(
            select(func.count(ImportIssue.id)).where(
                ImportIssue.import_job_id == job.id,
                ImportIssue.status == "open",
            )
        )
        or 0,
    )


def _library_workspace_record(library: str, row, project: Project, source: SourceFile | None) -> WorkspaceRecord:
    comparable = governance_comparability(project)
    source_ref = SourceRef(file_id=source.id, file_name=source.original_name, sheet_name=row.source_sheet, start_row=row.source_row, cell_range=str(row.source_row)) if source else None
    return WorkspaceRecord(
        id=row.id, library=library, data_type=row.data_type, name=row.name, code=row.code, specification=row.specification,
        description=row.payload.get("description"), unit=row.unit,
        quantity=DecimalValue(value=from_scaled(row.quantity_value, row.quantity_scale), scale=row.quantity_scale, unit=row.unit),
        unit_price=DecimalValue(value=from_scaled(row.unit_price_value, row.unit_price_scale), scale=row.unit_price_scale, currency="CNY"),
        total=DecimalValue(value=from_scaled(row.total_value, row.total_scale), scale=row.total_scale, currency="CNY"),
        project_id=project.id, project_name=project.name, project_version_id=row.project_version_id, region=project.region,
        pricing_date=project.pricing_date, specialty=project.specialty, pricing_mode=project.pricing_mode,
        result_stage=project.result_stage, comparability=comparable, data_status="published", price_context=project.price_context,
        warnings=record_warnings(project, link_status=row.payload.get("link_status")), source=source_ref, attributes=row.payload.get("attributes", row.payload),
    )


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    settings = get_settings()
    return HealthRead(
        status="ok",
        version=__version__,
        database=str(settings.database_path),
        fts5=True,
        session_token=settings.effective_session_token,
    )


@router.get("/dashboard")
def dashboard(session: DB) -> dict[str, int]:
    return {
        "projects": session.scalar(select(func.count(Project.id))) or 0,
        "published_versions": session.scalar(
            select(func.count(ProjectVersion.id)).where(ProjectVersion.status == "published")
        )
        or 0,
        "cost_items": session.scalar(select(func.count(CostItem.id))) or 0,
        "open_issues": session.scalar(
            select(func.count(ImportIssue.id)).where(ImportIssue.status == "open")
        )
        or 0,
    }


@router.post("/projects", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: DB) -> ProjectSummary:
    project = Project(
        name=payload.name,
        region=payload.region,
        pricing_date=payload.pricing_date,
        specialty=payload.specialty,
        pricing_mode=payload.pricing_mode,
        quota_version=payload.quota_version,
        result_stage=payload.result_stage,
        project_type=payload.project_type,
        construction_nature=payload.construction_nature,
        area_value=to_scaled(payload.area),
        area_unit=payload.area_unit,
        notes=payload.notes,
        profile=payload.profile,
    )
    session.add(project)
    session.commit()
    return _serialize_project(session, project)


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(session: DB) -> list[ProjectSummary]:
    projects = session.scalars(select(Project).order_by(desc(Project.created_at))).all()
    return [_serialize_project(session, project) for project in projects]


@router.patch("/projects/{project_id}/profile", response_model=ProjectSummary)
def update_project_profile(project_id: str, payload: ProjectProfileUpdate, session: DB) -> ProjectSummary:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    project.profile = {**project.profile, **payload.profile}
    session.add(AuditEvent(event_type="project.profile_updated", entity_type="project", entity_id=project.id, payload={"fields": sorted(payload.profile)}))
    session.commit()
    return _serialize_project(session, project)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project_detail(project_id: str, session: DB) -> ProjectDetail:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    versions = session.scalars(select(ProjectVersion).where(ProjectVersion.project_id == project_id).order_by(desc(ProjectVersion.version_no))).all()
    latest = versions[0] if versions else None
    from cost_data.models import FeeRate, MeasureItem, QuotaItem, ResourceItem
    counts = {"bill": 0, "quota": 0, "resource": 0, "measure": 0, "fee_rate": 0, "metric": 0}
    sources: list[SourceRef] = []
    metrics: list[Any] = []
    if latest:
        counts.update({
            "bill": session.scalar(select(func.count(CostItem.id)).where(CostItem.project_version_id == latest.id)) or 0,
            "quota": session.scalar(select(func.count(QuotaItem.id)).join(CostItem).where(CostItem.project_version_id == latest.id)) or 0,
            "resource": session.scalar(select(func.count(ResourceItem.id)).where(ResourceItem.project_version_id == latest.id)) or 0,
            "measure": session.scalar(select(func.count(MeasureItem.id)).where(MeasureItem.project_version_id == latest.id)) or 0,
            "fee_rate": session.scalar(select(func.count(FeeRate.id)).where(FeeRate.project_version_id == latest.id)) or 0,
            "metric": session.scalar(select(func.count(ProjectMetric.id)).where(ProjectMetric.project_version_id == latest.id)) or 0,
        })
        metrics = [serialize_metric(metric) for metric in session.scalars(select(ProjectMetric).where(ProjectMetric.project_version_id == latest.id).order_by(ProjectMetric.code)).all()]
        sources = [SourceRef(file_id=file.id, file_name=file.original_name, sheet_name="", start_row=0) for file in session.scalars(select(SourceFile).where(SourceFile.project_version_id == latest.id)).all()]
    return ProjectDetail(project=_serialize_project(session, project), versions=[_serialize_version(session, version) for version in versions], data_counts=counts, metrics=metrics, source_files=sources)


@router.get("/projects/{project_id}/versions", response_model=list[ProjectVersionRead])
def list_project_versions(project_id: str, session: DB) -> list[ProjectVersionRead]:
    versions = session.scalars(
        select(ProjectVersion).where(ProjectVersion.project_id == project_id).order_by(desc(ProjectVersion.version_no))
    ).all()
    return [_serialize_version(session, version) for version in versions]


@router.post("/imports", response_model=ImportRead, status_code=status.HTTP_202_ACCEPTED)
async def create_import(
    background_tasks: BackgroundTasks,
    session: DB,
    metadata_json: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    project_id: Annotated[str | None, Form()] = None,
) -> ImportRead:
    try:
        metadata = ProjectCreate.model_validate_json(metadata_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"项目元数据无效：{exc}") from exc
    if not files:
        raise HTTPException(status_code=422, detail="至少选择一个 Excel 文件")
    invalid = [file.filename for file in files if Path(file.filename or "").suffix.lower() not in {".xlsx", ".xlsm"}]
    if invalid:
        raise HTTPException(status_code=422, detail=f"暂不支持以下文件：{', '.join(invalid)}")
    project = session.get(Project, project_id) if project_id else None
    if project_id and not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not project:
        project = Project(
            name=metadata.name,
            region=metadata.region,
            pricing_date=metadata.pricing_date,
            specialty=metadata.specialty,
            pricing_mode=metadata.pricing_mode,
            quota_version=metadata.quota_version,
            result_stage=metadata.result_stage,
            project_type=metadata.project_type,
            construction_nature=metadata.construction_nature,
            area_value=to_scaled(metadata.area),
            area_unit=metadata.area_unit,
            notes=metadata.notes,
            profile=metadata.profile,
            price_context=metadata.price_context,
        )
        session.add(project)
        session.flush()
    version = ProjectVersion(
        project_id=project.id,
        version_no=next_version_no(session, project.id),
        status="draft",
        label="过程稿",
    )
    session.add(version)
    session.flush()
    job = ImportJob(
        project_id=project.id,
        project_version_id=version.id,
        status="queued",
        total_files=len(files),
    )
    session.add(job)
    session.flush()
    accepted_files = 0
    with tempfile.TemporaryDirectory(prefix="cost-data-import-") as temp_dir:
        for upload in files:
            safe_name = Path(upload.filename or "workbook.xlsx").name
            temp_path = Path(temp_dir) / safe_name
            with temp_path.open("wb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    handle.write(chunk)
            digest, relative, size = archive_file(temp_path, safe_name)
            duplicate = session.scalar(
                select(SourceFile)
                .join(ProjectVersion, ProjectVersion.id == SourceFile.project_version_id)
                .where(ProjectVersion.project_id == project.id, SourceFile.sha256 == digest)
            )
            if duplicate:
                session.add(
                    ImportIssue(
                        import_job_id=job.id,
                        severity="warning",
                        code="DUPLICATE_FILE",
                        message=f"文件内容与已导入文件相同，已跳过：{safe_name}",
                        suggested_action="无需重复导入",
                    )
                )
                continue
            session.add(
                SourceFile(
                    project_version_id=version.id,
                    import_job_id=job.id,
                    original_name=safe_name,
                    relative_path=relative,
                    sha256=digest,
                    size_bytes=size,
                )
            )
            accepted_files += 1
    if accepted_files == 0:
        session.rollback()
        raise HTTPException(status_code=409, detail="所选文件均已导入，未创建新版本")
    job.total_files = accepted_files
    session.add(AuditEvent(event_type="import.created", entity_type="import_job", entity_id=job.id, payload={"file_count": accepted_files}))
    session.commit()
    background_tasks.add_task(process_import_job, job.id)
    return _serialize_import(session, job)


@router.get("/imports", response_model=list[ImportRead])
def list_imports(session: DB) -> list[ImportRead]:
    jobs = session.scalars(select(ImportJob).order_by(desc(ImportJob.created_at)).limit(100)).all()
    return [_serialize_import(session, job) for job in jobs]


@router.get("/imports/{job_id}", response_model=ImportRead)
def get_import(job_id: str, session: DB) -> ImportRead:
    job = session.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return _serialize_import(session, job)


@router.get("/imports/{job_id}/parse-preview", response_model=ImportParsePreview)
def get_import_parse_preview(job_id: str, session: DB) -> ImportParsePreview:
    job = session.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return ImportParsePreview.model_validate(job.parse_preview or {})


@router.post("/imports/{job_id}/confirm-mapping", response_model=ImportRead)
def confirm_import_mapping(
    job_id: str,
    payload: ImportMappingConfirmation,
    background_tasks: BackgroundTasks,
    session: DB,
) -> ImportRead:
    job = session.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    if job.status != "mapping_review":
        raise HTTPException(status_code=409, detail="导入任务当前无需确认映射")
    job.parse_preview = {"tables": payload.tables}
    if payload.save_profile:
        save_parser_profiles(session, payload.tables)
    job.status = "queued"
    session.commit()
    background_tasks.add_task(process_import_job, job.id)
    return _serialize_import(session, job)


@router.post("/imports/{job_id}/ai-mapping-suggestion", response_model=ImportMappingSuggestion)
def suggest_import_mapping_for_job(job_id: str, session: DB) -> ImportMappingSuggestion:
    job = session.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    if job.status != "mapping_review":
        raise HTTPException(status_code=409, detail="仅待确认映射的导入任务可请求 AI 建议")
    try:
        return suggest_import_mapping(session, job.parse_preview)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/imports/{job_id}/issues", response_model=list[ImportIssueRead])
def list_import_issues(job_id: str, session: DB) -> list[ImportIssueRead]:
    return list(
        session.scalars(
            select(ImportIssue).where(ImportIssue.import_job_id == job_id).order_by(ImportIssue.status, ImportIssue.severity, ImportIssue.created_at)
        ).all()
    )


@router.patch("/imports/{job_id}/issues/{issue_id}", response_model=ImportIssueRead)
def resolve_import_issue(job_id: str, issue_id: str, payload: IssueResolve, session: DB) -> ImportIssue:
    issue = session.get(ImportIssue, issue_id)
    if not issue or issue.import_job_id != job_id:
        raise HTTPException(status_code=404, detail="导入问题不存在")
    issue.status = payload.status
    issue.resolution = payload.resolution
    session.commit()
    return issue


@router.post("/imports/{job_id}/publish", response_model=ProjectVersionRead)
def publish_import(job_id: str, session: DB) -> ProjectVersionRead:
    job = session.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    if job.status != "review":
        raise HTTPException(status_code=409, detail="导入任务尚未进入复核状态")
    blocking = session.scalar(
        select(func.count(ImportIssue.id)).where(
            ImportIssue.import_job_id == job.id,
            ImportIssue.status == "open",
            ImportIssue.severity == "error",
        )
    )
    quality = build_quality_report(session, job.project_version_id)
    blocking = max(blocking or 0, quality.summary["errors"])
    if blocking:
        raise HTTPException(status_code=409, detail=f"仍有 {blocking} 个错误未处理")
    version = session.get(ProjectVersion, job.project_version_id)
    if not version:
        raise HTTPException(status_code=404, detail="项目版本不存在")
    session.execute(
        update(ProjectVersion)
        .where(
            ProjectVersion.project_id == version.project_id,
            ProjectVersion.status == "published",
            ProjectVersion.id != version.id,
        )
        .values(status="superseded")
    )
    version.status = "published"
    version.label = "正式稿"
    version.published_at = datetime.now(timezone.utc)
    session.execute(update(CostItem).where(CostItem.project_version_id == version.id).values(data_status="published"))
    from cost_data.models import ResourceItem
    session.execute(update(ResourceItem).where(ResourceItem.project_version_id == version.id).values(data_status="published"))
    job.status = "completed"
    calculate_metrics(session, version.id)
    rebuild_fts(session, version.id)
    # Write library mirrors before exposing this version through the central index.
    # A failed mirror leaves the central transaction uncommitted and the version hidden.
    sync_version(session, version.id)
    session.add(AuditEvent(event_type="import.published", entity_type="project_version", entity_id=version.id, payload={"job_id": job.id}))
    session.commit()
    return _serialize_version(session, version)


@router.get("/cost-items/search", response_model=SearchResult)
def search_items(session: DB, intent: Annotated[SearchIntent, Query()]) -> SearchResult:
    return search_cost_items(session, intent)


@router.get("/workspace/search", response_model=WorkspaceSearchResult)
def workspace_search(session: DB, intent: Annotated[SearchIntent, Query()]) -> WorkspaceSearchResult:
    records = []
    requested = {intent.data_type} if intent.data_type != "all" else {"bill", "resource", "quota"}
    mapping = {"catalog": "bill", "resource": "resource", "quota": "quota"}
    for library in LIBRARIES:
        if mapping[library] not in requested:
            continue
        records.extend(_library_workspace_record(library, row, project, source) for row, project, source in search_library(session, library, intent))
    # Measures, fee rates and project metrics remain central metadata assets. Keep
    # them in the independent cross-library tab without duplicating the three
    # dedicated business-library record sets.
    if intent.data_type in {"all", "measure", "fee_rate", "metric"}:
        records.extend(record for record in search_workspace(session, intent).items if record.data_type in {"measure", "fee_rate", "metric"})
    records.sort(key=lambda record: (record.pricing_date, record.project_name, record.name), reverse=True)
    return WorkspaceSearchResult(items=records[intent.offset:intent.offset + intent.limit], total=len(records))


@router.get("/libraries", response_model=list[LibrarySummary])
def list_libraries(session: DB) -> list[LibrarySummary]:
    return [LibrarySummary(**summary) for summary in library_summaries(session)]


@router.get("/libraries/{library}/search", response_model=WorkspaceSearchResult)
def library_search(library: str, session: DB, intent: Annotated[SearchIntent, Query()]) -> WorkspaceSearchResult:
    if library not in LIBRARIES:
        raise HTTPException(status_code=404, detail="分库不存在")
    expected = {"catalog": "bill", "resource": "resource", "quota": "quota"}[library]
    if intent.data_type not in {"all", expected}:
        return WorkspaceSearchResult(items=[], total=0)
    records = [_library_workspace_record(library, row, project, source) for row, project, source in search_library(session, library, intent)]
    records.sort(key=lambda record: (record.pricing_date, record.project_name, record.name), reverse=True)
    return WorkspaceSearchResult(items=records[intent.offset:intent.offset + intent.limit], total=len(records))


@router.get("/libraries/{library}/records/{record_id}", response_model=LibraryRecordRead)
def library_record(library: str, record_id: str, session: DB) -> LibraryRecordRead:
    if library not in LIBRARIES:
        raise HTTPException(status_code=404, detail="分库不存在")
    row = get_library_record(library, record_id)
    version = session.get(ProjectVersion, row.project_version_id) if row else None
    project = session.get(Project, row.project_id) if row else None
    if not row or not version or version.status != "published" or not project:
        raise HTTPException(status_code=404, detail="分库记录不存在")
    source = session.get(SourceFile, row.source_file_id)
    return LibraryRecordRead(**_library_workspace_record(library, row, project, source).model_dump(), payload=row.payload)


@router.patch("/libraries/{library}/records/{record_id}", response_model=WorkspaceRecord)
def update_library_bill_record(library: str, record_id: str, payload: BillRecordUpdate, session: DB) -> WorkspaceRecord:
    """Correct a catalog record while retaining its source evidence and mirror identity."""
    if library != "catalog":
        raise HTTPException(status_code=405, detail="目前仅支持编辑清单库记录")
    row = get_library_record(library, record_id)
    version = session.get(ProjectVersion, row.project_version_id) if row else None
    project = session.get(Project, row.project_id) if row else None
    if not row or not version or version.status != "published" or not project:
        raise HTTPException(status_code=404, detail="分库记录不存在")
    item = session.get(CostItem, record_id)
    if not item:
        raise HTTPException(status_code=404, detail="清单原始记录不存在")

    fields = payload.model_fields_set
    for field in ("code", "name", "specification", "description", "unit"):
        if field in fields:
            setattr(item, field, getattr(payload, field))
    if "name" in fields and not item.name:
        raise HTTPException(status_code=422, detail="清单名称不能为空")
    for field, value_field, scale_field in (
        ("quantity", "quantity_value", "quantity_scale"),
        ("unit_price", "unit_price_value", "unit_price_scale"),
        ("total", "total_value", "total_scale"),
    ):
        if field in fields:
            try:
                setattr(item, value_field, to_scaled(getattr(payload, field), getattr(item, scale_field)))
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"{field} 必须是有效数字") from exc
    item.normalized_name = item.name.strip()
    session.add(AuditEvent(event_type="library_record.updated", entity_type="cost_item", entity_id=item.id, payload={"fields": sorted(fields)}))
    session.commit()

    # The catalog is an independent SQLite mirror. Rebuild this version only after
    # the canonical record has committed, so the edited value is immediately searchable.
    sync_version(session, version.id)
    refreshed = get_library_record(library, record_id)
    source = session.get(SourceFile, refreshed.source_file_id) if refreshed else None
    if not refreshed:
        raise HTTPException(status_code=500, detail="清单库同步失败")
    return _library_workspace_record(library, refreshed, project, source)


@router.get("/quality/projects/{version_id}", response_model=QualityReportRead)
def project_quality(version_id: str, session: DB) -> QualityReportRead:
    try:
        return build_quality_report(session, version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cost-items/{item_id}/source", response_model=SourceRef)
def get_item_source(item_id: str, session: DB) -> SourceRef:
    from cost_data.search import get_cost_item

    item = get_cost_item(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="清单项不存在")
    return item.source


@router.post("/comparisons", response_model=ComparisonRead)
def compare_items(payload: ComparisonRequest, session: DB) -> ComparisonRead:
    result = compare_cost_items(session, payload.cost_item_ids)
    if len(result.items) < 2:
        raise HTTPException(status_code=404, detail="至少需要两个有效清单项")
    return result


@router.post("/match-sessions", response_model=MatchSessionRead, status_code=status.HTTP_201_CREATED)
def create_match_session(payload: MatchSessionCreate, session: DB) -> MatchSessionRead:
    match_session = MatchSession(name=payload.name, query_items=[item.model_dump(mode="json") for item in payload.items])
    session.add(match_session)
    session.commit()
    return serialize_match_session(session, match_session)


@router.get("/match-sessions/{session_id}", response_model=MatchSessionRead)
def get_match_session(session_id: str, session: DB) -> MatchSessionRead:
    match_session = session.get(MatchSession, session_id)
    if not match_session:
        raise HTTPException(status_code=404, detail="匹配会话不存在")
    return serialize_match_session(session, match_session)


@router.post("/match-sessions/{session_id}/decisions", status_code=status.HTTP_201_CREATED)
def create_match_decision(session_id: str, payload: MatchDecisionCreate, session: DB) -> dict[str, str]:
    match_session = session.get(MatchSession, session_id)
    if not match_session:
        raise HTTPException(status_code=404, detail="匹配会话不存在")
    if payload.query_index >= len(match_session.query_items):
        raise HTTPException(status_code=422, detail="查询项序号无效")
    decision = MatchDecision(
        match_session_id=session_id,
        query_index=payload.query_index,
        candidate_cost_item_id=payload.candidate_cost_item_id,
        decision=payload.decision,
        note=payload.note,
    )
    session.add(decision)
    if payload.remember_rule and payload.decision == "accepted" and payload.candidate_cost_item_id:
        candidate = session.get(CostItem, payload.candidate_cost_item_id)
        query_item = match_session.query_items[payload.query_index]
        if candidate:
            session.add(
                NormalizationRule(
                    rule_type="synonym",
                    source_value=query_item["name"],
                    target_value=candidate.normalized_name or candidate.name,
                    conditions={"unit": query_item.get("unit")},
                    source="match_decision",
                )
            )
    session.commit()
    return {"id": decision.id, "status": "saved"}


@router.get("/metrics/projects/{version_id}")
def get_project_metrics(version_id: str, session: DB) -> list[Any]:
    metrics = session.scalars(
        select(ProjectMetric).where(ProjectMetric.project_version_id == version_id).order_by(ProjectMetric.code)
    ).all()
    return [serialize_metric(metric) for metric in metrics]


@router.post("/metrics/projects/{version_id}/recalculate")
def recalculate_project_metrics(version_id: str, session: DB) -> list[Any]:
    try:
        metrics = calculate_metrics(session, version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return [serialize_metric(metric) for metric in metrics]


@router.get("/benchmarks/metrics/{metric_code}", response_model=BenchmarkRead)
def metric_benchmark(metric_code: str, session: DB, project_type: str | None = None, specialty: str | None = None) -> BenchmarkRead:
    rows = session.execute(
        select(ProjectMetric, Project, ProjectVersion)
        .join(ProjectVersion, ProjectVersion.id == ProjectMetric.project_version_id)
        .join(Project, Project.id == ProjectVersion.project_id)
        .where(ProjectMetric.code == metric_code, ProjectVersion.status == "published", ProjectMetric.value.is_not(None))
    ).all()
    samples = []
    for metric, project, version in rows:
        ready = project.project_type and all(project.profile.get(field) for field in ("structure_form", "area_basis", "above_ground_area", "underground_area"))
        if not ready or (project_type and project.project_type != project_type) or (specialty and project.specialty != specialty):
            continue
        samples.append({"project_id": project.id, "project_name": project.name, "project_version_id": version.id, "region": project.region, "pricing_date": project.pricing_date, "value": from_scaled(metric.value, metric.scale), "unit": metric.unit})
    values = [float(sample["value"]) for sample in samples if sample["value"] is not None]
    unit = samples[0]["unit"] if samples else None
    def value_at(percentile: float) -> DecimalValue:
        if not values: return DecimalValue(value=None, unit=unit)
        return DecimalValue(value=str(statistics.quantiles(values, n=4, method="inclusive")[int(percentile) - 1]) if len(values) > 1 else str(values[0]), unit=unit)
    return BenchmarkRead(metric_code=metric_code, sample_count=len(values), mean=DecimalValue(value=str(statistics.mean(values)) if values else None, unit=unit), p25=value_at(1), p50=value_at(2), p75=value_at(3), samples=samples)


@router.get("/normalization-rules", response_model=list[NormalizationRuleRead])
def list_rules(session: DB) -> list[NormalizationRule]:
    return list(session.scalars(select(NormalizationRule).order_by(desc(NormalizationRule.created_at))).all())


@router.post("/normalization-rules", response_model=NormalizationRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(payload: NormalizationRuleCreate, session: DB) -> NormalizationRule:
    rule = NormalizationRule(**payload.model_dump(), source="user")
    session.add(rule)
    session.commit()
    return rule


@router.patch("/normalization-rules/{rule_id}", response_model=NormalizationRuleRead)
def update_rule(rule_id: str, payload: RuleUpdate, session: DB) -> NormalizationRule:
    rule = session.get(NormalizationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.enabled = payload.enabled
    session.commit()
    return rule


@router.get("/unit-conversions", response_model=list[UnitConversionRead])
def list_unit_conversions(session: DB) -> list[UnitConversionRead]:
    return [UnitConversionRead(id=rule.id, source_unit=rule.source_unit, target_unit=rule.target_unit, factor=from_scaled(rule.factor_value, rule.factor_scale) or "0", basis=rule.basis, enabled=rule.enabled) for rule in session.scalars(select(UnitConversion).order_by(UnitConversion.source_unit)).all()]


@router.post("/unit-conversions", response_model=UnitConversionRead, status_code=status.HTTP_201_CREATED)
def create_unit_conversion(payload: UnitConversionCreate, session: DB) -> UnitConversionRead:
    if conversion_factor(session, payload.source_unit, payload.target_unit) is not None:
        raise HTTPException(status_code=409, detail="该单位换算规则已存在")
    rule = UnitConversion(source_unit=payload.source_unit, target_unit=payload.target_unit, factor_value=to_scaled(payload.factor) or 0, basis=payload.basis)
    session.add(rule)
    session.commit()
    return UnitConversionRead(id=rule.id, source_unit=rule.source_unit, target_unit=rule.target_unit, factor=from_scaled(rule.factor_value, rule.factor_scale) or "0", basis=rule.basis, enabled=rule.enabled)


@router.patch("/unit-conversions/{conversion_id}", response_model=UnitConversionRead)
def update_unit_conversion(conversion_id: str, payload: UnitConversionUpdate, session: DB) -> UnitConversionRead:
    rule = session.get(UnitConversion, conversion_id)
    if not rule:
        raise HTTPException(status_code=404, detail="单位换算规则不存在")
    rule.enabled = payload.enabled
    session.commit()
    return UnitConversionRead(id=rule.id, source_unit=rule.source_unit, target_unit=rule.target_unit, factor=from_scaled(rule.factor_value, rule.factor_scale) or "0", basis=rule.basis, enabled=rule.enabled)


@router.get("/metric-templates", response_model=list[MetricTemplateRead])
def list_metric_templates(session: DB) -> list[MetricTemplate]:
    return list(session.scalars(select(MetricTemplate).order_by(MetricTemplate.code)).all())


@router.post("/metric-templates", response_model=MetricTemplateRead, status_code=status.HTTP_201_CREATED)
def create_metric_template(payload: MetricTemplateCreate, session: DB) -> MetricTemplate:
    if session.scalar(select(MetricTemplate).where(MetricTemplate.code == payload.code)):
        raise HTTPException(status_code=409, detail="指标编码已存在")
    template = MetricTemplate(**payload.model_dump())
    session.add(template)
    session.commit()
    return template


@router.get("/exports/reference-prices")
def download_reference_prices(session: DB, ids: Annotated[list[str], Query()], library: str | None = None) -> FileResponse:
    if library and library not in LIBRARIES:
        raise HTTPException(status_code=404, detail="分库不存在")
    path = export_reference_prices(session, ids, library)
    return FileResponse(path, filename=path.name)


@router.get("/exports/imports/{job_id}")
def download_quality_report(job_id: str, session: DB) -> FileResponse:
    path = export_quality_report(session, job_id)
    return FileResponse(path, filename=path.name)


@router.post("/backups", response_model=BackupRead, status_code=status.HTTP_201_CREATED)
def create_manual_backup(payload: BackupCreate, session: DB) -> BackupRead:
    try:
        result = create_backup(Path(payload.target_directory), payload.kind)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"备份失败：{exc}") from exc
    setting = session.get(AppSetting, "backup")
    if setting:
        setting.value = {"directory": payload.target_directory}
    else:
        session.add(AppSetting(key="backup", value={"directory": payload.target_directory}))
    session.commit()
    return BackupRead(**result)


@router.get("/backups", response_model=list[BackupRead])
def list_backups(session: DB) -> list[BackupRead]:
    setting = session.get(AppSetting, "backup")
    if not setting or not setting.value.get("directory"):
        return []
    target = Path(setting.value["directory"]).expanduser()
    results = []
    for manifest_path in sorted(target.glob("*/manifest.json"), reverse=True):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            results.append(BackupRead(**data, path=str(manifest_path.parent)))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return results


@router.post("/restores")
def restore_backup(payload: RestoreCreate) -> dict[str, Any]:
    try:
        result = stage_restore(Path(payload.backup_path))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"恢复校验失败：{exc}") from exc
    return {"status": "restart_required", "backup_id": result["id"]}


@router.get("/settings/ai", response_model=AISettingsRead)
def get_ai_settings(session: DB) -> AISettingsRead:
    base_url, model = get_ai_configuration(session)
    return AISettingsRead(model=model, base_url=base_url, has_api_key=bool(get_api_key()))


@router.put("/settings/ai", response_model=AISettingsRead)
def update_ai_settings(payload: AISettingsUpdate, session: DB) -> AISettingsRead:
    set_ai_configuration(session, payload.base_url, payload.model)
    if payload.api_key:
        try:
            set_api_key(payload.api_key)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"无法写入 macOS Keychain：{exc}") from exc
    session.commit()
    return AISettingsRead(model=payload.model, base_url=payload.base_url, has_api_key=bool(get_api_key()))


@router.post("/ai/preview", response_model=AIPreviewRead)
def preview_ai_payload(payload: AIPreviewRequest, session: DB) -> AIPreviewRead:
    consent = session.scalar(select(AIConsent).where(AIConsent.capability == payload.capability))
    redacted = redact_payload(payload.payload)
    return AIPreviewRead(
        capability=payload.capability,
        redacted_payload=redacted,
        field_names=sorted(redacted.keys()),
        consent_required=not bool(consent and consent.approved and consent.remember),
    )


@router.put("/ai/consents")
def update_ai_consent(payload: AIConsentUpdate, session: DB) -> dict[str, str]:
    consent = session.scalar(select(AIConsent).where(AIConsent.capability == payload.capability))
    if consent:
        consent.approved = payload.approved
        consent.remember = payload.remember
        consent.field_names = payload.field_names
    else:
        consent = AIConsent(**payload.model_dump())
        session.add(consent)
    session.commit()
    return {"status": "saved"}


@router.post("/ai/search-intent", response_model=SearchIntent)
def ai_search_intent(payload: NaturalLanguageQuery, session: DB) -> SearchIntent:
    try:
        return parse_search_intent(session, payload.text)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ai/candidate-review", response_model=AISuggestion)
def ai_candidate_review(payload: CandidateReviewRequest, session: DB) -> AISuggestion:
    try:
        return review_candidates(session, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/ai/calls", response_model=list[AICallRead])
def list_ai_calls(session: DB) -> list[AICall]:
    return list(session.scalars(select(AICall).order_by(desc(AICall.created_at)).limit(100)).all())
