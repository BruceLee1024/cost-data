from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(120), nullable=False, default="西安")
    pricing_date: Mapped[str] = mapped_column(String(32), nullable=False)
    specialty: Mapped[str] = mapped_column(String(120), nullable=False)
    pricing_mode: Mapped[str] = mapped_column(String(120), nullable=False)
    quota_version: Mapped[str | None] = mapped_column(String(120))
    result_stage: Mapped[str] = mapped_column(String(120), nullable=False)
    project_type: Mapped[str | None] = mapped_column(String(120))
    construction_nature: Mapped[str | None] = mapped_column(String(120))
    area_value: Mapped[int | None] = mapped_column(BigInteger)
    area_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    area_unit: Mapped[str] = mapped_column(String(32), default="m2", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # Kept as a typed JSON document so historical projects can be enriched gradually.
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Price meaning belongs to the historical project, never to an inferred price.
    price_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    versions: Mapped[list[ProjectVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectVersion(Base, TimestampMixin):
    __tablename__ = "project_versions"
    __table_args__ = (Index("ix_project_version_project_no", "project_id", "version_no", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), default="过程稿", nullable=False)
    published_at: Mapped[datetime | None]

    project: Mapped[Project] = relationship(back_populates="versions")
    source_files: Mapped[list[SourceFile]] = relationship(
        back_populates="project_version", cascade="all, delete-orphan"
    )
    cost_items: Mapped[list[CostItem]] = relationship(
        back_populates="project_version", cascade="all, delete-orphan"
    )


class ImportJob(Base, TimestampMixin):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)
    parse_preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    issues: Mapped[list[ImportIssue]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )


class SourceFile(Base, TimestampMixin):
    __tablename__ = "source_files"
    __table_args__ = (Index("ix_source_file_version_hash", "project_version_id", "sha256", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    import_job_id: Mapped[str] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(700), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_type: Mapped[str] = mapped_column(String(80), default="unknown", nullable=False)
    sheet_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    project_version: Mapped[ProjectVersion] = relationship(back_populates="source_files")


class ParserProfile(Base, TimestampMixin):
    __tablename__ = "parser_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    report_type: Mapped[str] = mapped_column(String(80), nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ImportIssue(Base, TimestampMixin):
    __tablename__ = "import_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    import_job_id: Mapped[str] = mapped_column(ForeignKey("import_jobs.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(240))
    cell_range: Mapped[str | None] = mapped_column(String(80))
    suggested_action: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text)

    import_job: Mapped[ImportJob] = relationship(back_populates="issues")


class CostItem(Base, TimestampMixin):
    __tablename__ = "cost_items"
    __table_args__ = (
        Index("ix_cost_item_search", "project_version_id", "code", "name"),
        Index("ix_cost_item_source_row", "source_file_id", "sheet_name", "source_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(32), default="bill", nullable=False)
    code: Mapped[str | None] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text)
    specification: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40), index=True)
    quantity_value: Mapped[int | None] = mapped_column(BigInteger)
    quantity_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    unit_price_value: Mapped[int | None] = mapped_column(BigInteger)
    unit_price_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    total_value: Mapped[int | None] = mapped_column(BigInteger)
    total_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    currency: Mapped[str] = mapped_column(String(12), default="CNY", nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_row: Mapped[int | None]
    source_cells: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    import_attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    hierarchy_path: Mapped[str | None] = mapped_column(Text)
    data_status: Mapped[str] = mapped_column(String(24), default="parsed", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)

    project_version: Mapped[ProjectVersion] = relationship(back_populates="cost_items")
    components: Mapped[list[RateComponent]] = relationship(
        back_populates="cost_item", cascade="all, delete-orphan"
    )
    quotas: Mapped[list[QuotaItem]] = relationship(back_populates="cost_item", cascade="all, delete-orphan")


class RateComponent(Base, TimestampMixin):
    __tablename__ = "rate_components"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cost_item_id: Mapped[str] = mapped_column(ForeignKey("cost_items.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    value: Mapped[int | None] = mapped_column(BigInteger)
    scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"))
    sheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    link_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    link_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    cost_item: Mapped[CostItem] = relationship(back_populates="components")


class QuotaItem(Base, TimestampMixin):
    __tablename__ = "quota_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cost_item_id: Mapped[str] = mapped_column(ForeignKey("cost_items.id", ondelete="CASCADE"), index=True)
    code: Mapped[str | None] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    consumption_value: Mapped[int | None] = mapped_column(BigInteger)
    consumption_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"))
    sheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    link_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    link_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    cost_item: Mapped[CostItem] = relationship(back_populates="quotas")


class ResourceItem(Base, TimestampMixin):
    __tablename__ = "resource_items"
    __table_args__ = (Index("ix_resource_project_name", "project_version_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str | None] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    specification: Mapped[str | None] = mapped_column(String(500))
    unit: Mapped[str | None] = mapped_column(String(40))
    quantity_value: Mapped[int | None] = mapped_column(BigInteger)
    quantity_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    price_value: Mapped[int | None] = mapped_column(BigInteger)
    price_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    amount_value: Mapped[int | None] = mapped_column(BigInteger)
    amount_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_category: Mapped[str | None] = mapped_column(String(120))
    source_cells: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    data_status: Mapped[str] = mapped_column(String(24), default="parsed", nullable=False, index=True)


class MeasureItem(Base, TimestampMixin):
    __tablename__ = "measure_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_value: Mapped[int | None] = mapped_column(BigInteger)
    amount_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)


class FeeRate(Base, TimestampMixin):
    __tablename__ = "fee_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    rate_value: Mapped[int | None] = mapped_column(BigInteger)
    rate_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    basis: Mapped[str | None] = mapped_column(String(500))
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id", ondelete="CASCADE"))
    sheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)


class ProjectMetric(Base, TimestampMixin):
    __tablename__ = "project_metrics"
    __table_args__ = (Index("ix_metric_version_code", "project_version_id", "code", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_version_id: Mapped[str] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[int | None] = mapped_column(BigInteger)
    scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    numerator_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    denominator_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="calculated", nullable=False)


class UnitConversion(Base, TimestampMixin):
    __tablename__ = "unit_conversions"
    __table_args__ = (Index("ix_unit_conversion_source_target", "source_unit", "target_unit", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    target_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    factor_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    factor_scale: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    basis: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MetricTemplate(Base, TimestampMixin):
    __tablename__ = "metric_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NormalizationRule(Base, TimestampMixin):
    __tablename__ = "normalization_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_value: Mapped[str] = mapped_column(String(500), nullable=False)
    target_value: Mapped[str] = mapped_column(String(500), nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="user", nullable=False)


class MatchSession(Base, TimestampMixin):
    __tablename__ = "match_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    query_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)


class MatchDecision(Base, TimestampMixin):
    __tablename__ = "match_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    match_session_id: Mapped[str] = mapped_column(ForeignKey("match_sessions.id", ondelete="CASCADE"), index=True)
    query_index: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_cost_item_id: Mapped[str | None] = mapped_column(ForeignKey("cost_items.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)


class AIConsent(Base, TimestampMixin):
    __tablename__ = "ai_consents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    capability: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remember: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    field_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class AICall(Base):
    __tablename__ = "ai_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek", nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
