from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DecimalValue(APIModel):
    value: str | None
    scale: int = 6
    unit: str | None = None
    currency: str | None = None


class SourceRef(APIModel):
    file_id: str
    file_name: str
    sheet_name: str
    start_row: int
    end_row: int | None = None
    cell_range: str | None = None
    field_cells: dict[str, str] = Field(default_factory=dict)


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=240)
    region: str = "西安"
    pricing_date: str
    specialty: str
    pricing_mode: str
    quota_version: str | None = None
    result_stage: str
    project_type: str | None = None
    construction_nature: str | None = None
    area: str | None = None
    area_unit: str = "m2"
    notes: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict)
    price_context: dict[str, Any] = Field(default_factory=dict)


class ProjectProfileUpdate(APIModel):
    profile: dict[str, Any] = Field(default_factory=dict)


class ProjectSummary(APIModel):
    id: str
    name: str
    region: str
    pricing_date: str
    specialty: str
    pricing_mode: str
    result_stage: str
    project_type: str | None
    profile: dict[str, Any] = Field(default_factory=dict)
    price_context: dict[str, Any] = Field(default_factory=dict)
    comparability: Literal["searchable", "restricted", "benchmark_candidate"] = "restricted"
    area: DecimalValue
    latest_version_id: str | None = None
    latest_version_no: int | None = None
    latest_status: str | None = None
    item_count: int = 0
    issue_count: int = 0
    created_at: datetime


class ProjectVersionRead(APIModel):
    id: str
    project_id: str
    version_no: int
    status: str
    label: str
    published_at: datetime | None
    created_at: datetime
    file_count: int = 0
    item_count: int = 0


class ProjectDetail(APIModel):
    project: ProjectSummary
    versions: list[ProjectVersionRead]
    data_counts: dict[str, int]
    metrics: list["MetricRead"]
    source_files: list[SourceRef]


class ImportRead(APIModel):
    id: str
    project_id: str
    project_version_id: str
    status: str
    progress: int
    total_files: int
    processed_files: int
    error_summary: str | None
    parse_preview_available: bool = False
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    open_issue_count: int = 0


class ImportIssueRead(APIModel):
    id: str
    import_job_id: str
    source_file_id: str | None
    severity: str
    code: str
    message: str
    sheet_name: str | None
    cell_range: str | None
    suggested_action: str | None
    status: str
    resolution: str | None
    created_at: datetime


class IssueResolve(APIModel):
    status: Literal["resolved", "ignored"]
    resolution: str = Field(min_length=1, max_length=1000)


class ImportMappingConfirmation(APIModel):
    tables: list[dict[str, Any]] = Field(min_length=1)
    save_profile: bool = False


class ImportParsePreview(APIModel):
    tables: list[dict[str, Any]] = Field(default_factory=list)


class CostComponentRead(APIModel):
    id: str
    category: str
    name: str
    amount: DecimalValue
    source: SourceRef


class CostItemRead(APIModel):
    id: str
    project_id: str
    project_name: str
    project_version_id: str
    item_type: str
    code: str | None
    name: str
    normalized_name: str
    description: str | None
    specification: str | None
    unit: str | None
    quantity: DecimalValue
    unit_price: DecimalValue
    total: DecimalValue
    region: str
    pricing_date: str
    specialty: str
    pricing_mode: str
    result_stage: str
    source: SourceRef
    import_attributes: dict[str, Any] = Field(default_factory=dict)
    components: list[CostComponentRead] = Field(default_factory=list)


class SearchIntent(APIModel):
    query: str | None = None
    region: str | None = None
    pricing_date_from: str | None = None
    pricing_date_to: str | None = None
    specialty: str | None = None
    project_type: str | None = None
    pricing_mode: str | None = None
    result_stage: str | None = None
    unit: str | None = None
    code: str | None = None
    specification: str | None = None
    price_min: str | None = None
    price_max: str | None = None
    tax_inclusion: str | None = None
    price_type: str | None = None
    price_source_status: Literal["complete", "incomplete"] | None = None
    reference_scope: Literal["available", "restricted", "all"] | None = None
    sort_by: Literal["reference", "unit_price", "quantity", "pricing_date"] = "reference"
    data_type: Literal["bill", "quota", "resource", "measure", "fee_rate", "metric", "all"] = "all"
    resource_kind: Literal["labor", "material", "machine"] | None = None
    data_status: Literal["raw", "parsed", "reviewed", "published", "deprecated", "restricted"] | None = None
    cursor: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class SearchResult(APIModel):
    items: list[CostItemRead]
    next_cursor: str | None
    total: int


class ComparisonRequest(APIModel):
    cost_item_ids: list[str] = Field(min_length=2, max_length=20)


class ComparisonRead(APIModel):
    items: list[CostItemRead]
    sample_count: int
    min_price: DecimalValue
    median_price: DecimalValue
    max_price: DecimalValue
    warnings: list[str]


class MatchQueryItem(APIModel):
    code: str | None = None
    name: str = Field(min_length=1)
    specification: str | None = None
    unit: str | None = None
    specialty: str | None = None


class MatchSessionCreate(APIModel):
    name: str = Field(min_length=1, max_length=240)
    items: list[MatchQueryItem] = Field(min_length=1, max_length=500)


class ScorePart(APIModel):
    label: str
    score: int
    reason: str


class MatchCandidate(APIModel):
    cost_item: CostItemRead
    total_score: int
    score_parts: list[ScorePart]
    exclusions: list[str]


class MatchQueryResult(APIModel):
    query_index: int
    query: MatchQueryItem
    candidates: list[MatchCandidate]


class MatchSessionRead(APIModel):
    id: str
    name: str
    status: str
    created_at: datetime
    results: list[MatchQueryResult]


class MatchDecisionCreate(APIModel):
    query_index: int = Field(ge=0)
    candidate_cost_item_id: str | None = None
    decision: Literal["accepted", "rejected", "unmatched"]
    note: str | None = None
    remember_rule: bool = False


class MetricRead(APIModel):
    id: str
    code: str
    name: str
    value: DecimalValue
    formula: str
    numerator_source: dict[str, Any]
    denominator_source: dict[str, Any]
    status: str


class BenchmarkRead(APIModel):
    metric_code: str
    sample_count: int
    mean: DecimalValue
    p25: DecimalValue
    p50: DecimalValue
    p75: DecimalValue
    samples: list[dict[str, Any]]


class WorkspaceRecord(APIModel):
    id: str
    library: Literal["catalog", "resource", "quota"] | None = None
    data_type: str
    name: str
    code: str | None = None
    specification: str | None = None
    description: str | None = None
    unit: str | None = None
    quantity: DecimalValue
    unit_price: DecimalValue
    total: DecimalValue
    project_id: str
    project_name: str
    project_version_id: str
    region: str
    pricing_date: str
    specialty: str
    pricing_mode: str
    result_stage: str
    comparability: Literal["searchable", "restricted", "benchmark_candidate"]
    data_status: Literal["raw", "parsed", "reviewed", "published", "deprecated"] = "published"
    price_context: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    source: SourceRef | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class WorkspaceSearchResult(APIModel):
    items: list[WorkspaceRecord]
    total: int
    available_count: int = 0
    restricted_count: int = 0


class LibrarySummary(APIModel):
    key: Literal["catalog", "resource", "quota"]
    name: str
    database: str
    status: str
    record_count: int
    project_count: int
    updated_at: datetime | None = None


class LibraryRecordRead(WorkspaceRecord):
    payload: dict[str, Any] = Field(default_factory=dict)


class BillRecordUpdate(APIModel):
    """User-managed corrections for a published bill-library record."""

    code: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, max_length=500)
    specification: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=20000)
    unit: str | None = Field(default=None, max_length=40)
    quantity: str | None = None
    unit_price: str | None = None
    total: str | None = None


class UnitConversionCreate(APIModel):
    source_unit: str = Field(min_length=1, max_length=40)
    target_unit: str = Field(min_length=1, max_length=40)
    factor: str
    basis: str = Field(min_length=1, max_length=500)


class UnitConversionRead(UnitConversionCreate):
    id: str
    enabled: bool


class UnitConversionUpdate(APIModel):
    enabled: bool


class MetricTemplateCreate(APIModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    formula: str = Field(min_length=1)
    description: str | None = None


class MetricTemplateRead(MetricTemplateCreate):
    id: str
    enabled: bool


class QualityIssueRead(APIModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    status: str = "open"
    project_version_id: str
    source: SourceRef | None = None


class QualityReportRead(APIModel):
    project_version_id: str
    publishable: bool
    summary: dict[str, int]
    issues: list[QualityIssueRead]


class NormalizationRuleCreate(APIModel):
    rule_type: Literal["synonym", "unit", "classification", "forbidden_match"]
    source_value: str = Field(min_length=1, max_length=500)
    target_value: str = Field(min_length=1, max_length=500)
    conditions: dict[str, Any] = Field(default_factory=dict)


class NormalizationRuleRead(NormalizationRuleCreate):
    id: str
    enabled: bool
    source: str
    created_at: datetime


class RuleUpdate(APIModel):
    enabled: bool


class BackupCreate(APIModel):
    target_directory: str
    kind: Literal["manual", "daily", "weekly"] = "manual"


class BackupRead(APIModel):
    id: str
    path: str
    kind: str
    created_at: datetime
    database_sha256: str
    file_count: int
    status: str


class RestoreCreate(APIModel):
    backup_path: str


class AISettingsRead(APIModel):
    provider: str = "deepseek"
    model: str
    base_url: str
    has_api_key: bool


class AISettingsUpdate(APIModel):
    model: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, min_length=8)

    @field_validator("base_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("模型接口必须使用 HTTPS")
        return value.rstrip("/")


class AIPreviewRequest(APIModel):
    capability: Literal["search_intent", "candidate_review", "import_parsing"]
    payload: dict[str, Any]


class AIPreviewRead(APIModel):
    capability: str
    redacted_payload: dict[str, Any]
    field_names: list[str]
    consent_required: bool


class AIConsentUpdate(APIModel):
    capability: Literal["search_intent", "candidate_review", "import_parsing"]
    approved: bool
    remember: bool = True
    field_names: list[str] = Field(default_factory=list)


class NaturalLanguageQuery(APIModel):
    text: str = Field(min_length=2, max_length=2000)


class CandidateReviewRequest(APIModel):
    query_item: MatchQueryItem
    candidates: list[MatchCandidate] = Field(min_length=1, max_length=10)


class AISuggestion(APIModel):
    suggestion: str
    uncertainties: list[str] = Field(default_factory=list)
    confidence_reason: str
    recommended_candidate_id: str | None = None
    model: str | None = None
    prompt_version: str = "v1"
    confirmation_status: Literal["pending", "accepted", "rejected"] = "pending"


class ImportMappingSuggestion(APIModel):
    tables: list[dict[str, Any]] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    confidence_reason: str
    confirmation_status: Literal["pending"] = "pending"


class AICallRead(APIModel):
    id: str
    capability: str
    provider: str
    model: str
    status: str
    error: str | None
    latency_ms: int | None
    created_at: datetime


class HealthRead(APIModel):
    status: str
    version: str
    database: str
    fts5: bool
    session_token: str
