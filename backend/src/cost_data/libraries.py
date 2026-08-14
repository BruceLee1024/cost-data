"""Independent SQLite stores for the user-visible cost libraries.

The application intentionally keeps project, import and source-file metadata in the
central database.  Library rows therefore use stable UUID references rather than
cross-database foreign keys; the service layer resolves those references on read.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import BigInteger, JSON, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from cost_data.config import get_settings
from cost_data.models import CostItem, Project, ProjectVersion, QuotaItem, ResourceItem, SourceFile
from cost_data.governance import comparability

LibraryName = Literal["catalog", "resource", "quota"]
LIBRARIES: tuple[LibraryName, ...] = ("catalog", "resource", "quota")
LIBRARY_LABELS = {"catalog": "清单库", "resource": "工料机库", "quota": "定额库"}


class LibraryBase(DeclarativeBase):
    pass


class LibraryRecord(LibraryBase):
    __tablename__ = "library_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    project_version_id: Mapped[str] = mapped_column(String(36), index=True)
    source_file_id: Mapped[str] = mapped_column(String(36), index=True)
    data_type: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str | None] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    specification: Mapped[str | None] = mapped_column(String(500))
    unit: Mapped[str | None] = mapped_column(String(40), index=True)
    quantity_value: Mapped[int | None] = mapped_column(BigInteger)
    quantity_scale: Mapped[int] = mapped_column(default=6)
    unit_price_value: Mapped[int | None] = mapped_column(BigInteger)
    unit_price_scale: Mapped[int] = mapped_column(default=6)
    total_value: Mapped[int | None] = mapped_column(BigInteger)
    total_scale: Mapped[int] = mapped_column(default=6)
    source_sheet: Mapped[str] = mapped_column(String(240))
    source_row: Mapped[int] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), nullable=False)


_engines: dict[str, Any] = {}
_sessions: dict[str, sessionmaker[Session]] = {}


def _session_factory(library: LibraryName) -> sessionmaker[Session]:
    if library not in _sessions:
        path = get_settings().library_paths[library]
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30}, pool_pre_ping=True)
        LibraryBase.metadata.create_all(engine)
        _engines[library] = engine
        _sessions[library] = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    return _sessions[library]


def init_libraries() -> None:
    for library in LIBRARIES:
        _session_factory(library)


def _record_from_cost(item: CostItem, project_id: str) -> LibraryRecord:
    return LibraryRecord(
        id=item.id, project_id=project_id, project_version_id=item.project_version_id, source_file_id=item.source_file_id,
        data_type="bill", code=item.code, name=item.name, specification=item.specification, unit=item.unit,
        quantity_value=item.quantity_value, quantity_scale=item.quantity_scale, unit_price_value=item.unit_price_value,
        unit_price_scale=item.unit_price_scale, total_value=item.total_value, total_scale=item.total_scale,
        source_sheet=item.sheet_name, source_row=item.source_row,
        payload={"item_type": item.item_type, "description": item.description, "attributes": item.import_attributes,
                 "source_cells": item.source_cells, "hierarchy_path": item.hierarchy_path,
                 "data_status": item.data_status,
                 "components": [{"id": c.id, "category": c.category, "name": c.name, "value": c.value, "scale": c.scale,
                                 "link_status": c.link_status, "link_evidence": c.link_evidence} for c in item.components]},
    )


def _record_from_resource(item: ResourceItem, project_id: str) -> LibraryRecord:
    return LibraryRecord(
        id=item.id, project_id=project_id, project_version_id=item.project_version_id, source_file_id=item.source_file_id,
        data_type="resource", code=item.code, name=item.name, specification=item.specification, unit=item.unit,
        quantity_value=item.quantity_value, quantity_scale=item.quantity_scale, unit_price_value=item.price_value,
        unit_price_scale=item.price_scale, total_value=item.amount_value, total_scale=item.amount_scale,
        source_sheet=item.sheet_name, source_row=item.source_row,
        payload={"kind": item.kind, "source_category": item.source_category, "source_cells": item.source_cells, "data_status": item.data_status},
    )


def _record_from_quota(item: QuotaItem, project_id: str, version_id: str) -> LibraryRecord:
    return LibraryRecord(
        id=item.id, project_id=project_id, project_version_id=version_id, source_file_id=item.source_file_id,
        data_type="quota", code=item.code, name=item.name, specification=None, unit=item.unit,
        quantity_value=item.consumption_value, quantity_scale=item.consumption_scale, unit_price_value=None,
        total_value=None, source_sheet=item.sheet_name, source_row=item.source_row,
        payload={"catalog_item_id": item.cost_item_id, "link_status": item.link_status, "link_evidence": item.link_evidence},
    )


def sync_version(session: Session, version_id: str) -> None:
    """Replace one version's mirrors; safe to retry after an interrupted publication."""
    version = session.get(ProjectVersion, version_id)
    if not version:
        raise ValueError("项目版本不存在")
    records: dict[LibraryName, list[LibraryRecord]] = {"catalog": [], "resource": [], "quota": []}
    for item in session.scalars(select(CostItem).where(CostItem.project_version_id == version_id)).unique().all():
        records["catalog"].append(_record_from_cost(item, version.project_id))
    for item in session.scalars(select(ResourceItem).where(ResourceItem.project_version_id == version_id)).all():
        records["resource"].append(_record_from_resource(item, version.project_id))
    quota_query = select(QuotaItem).join(CostItem).where(CostItem.project_version_id == version_id)
    for item in session.scalars(quota_query).all():
        records["quota"].append(_record_from_quota(item, version.project_id, version_id))
    for library, rows in records.items():
        with _session_factory(library)() as target:
            target.execute(delete(LibraryRecord).where(LibraryRecord.project_version_id == version_id))
            target.add_all(rows)
            target.commit()


def sync_published_versions(session: Session) -> None:
    for version_id in session.scalars(select(ProjectVersion.id).where(ProjectVersion.status == "published")).all():
        sync_version(session, version_id)


def _allowed(record: LibraryRecord, project: Project, intent: Any) -> bool:
    if intent.region and project.region != intent.region: return False
    if intent.specialty and project.specialty != intent.specialty: return False
    if intent.project_type and project.project_type != intent.project_type: return False
    if intent.pricing_mode and project.pricing_mode != intent.pricing_mode: return False
    if intent.result_stage and project.result_stage != intent.result_stage: return False
    if intent.pricing_date_from and project.pricing_date < intent.pricing_date_from: return False
    if intent.pricing_date_to and project.pricing_date > intent.pricing_date_to: return False
    if intent.unit and record.unit != intent.unit: return False
    if intent.resource_kind and record.payload.get("kind") != intent.resource_kind: return False
    if intent.data_status == "published" and record.payload.get("data_status") not in {None, "published"}:
        return False
    if intent.data_status == "restricted" and project.price_context.get("tax_inclusion") and project.price_context.get("price_type") and project.price_context.get("price_source"):
        return False
    if intent.tax_inclusion and project.price_context.get("tax_inclusion") != intent.tax_inclusion: return False
    if intent.price_type and project.price_context.get("price_type") != intent.price_type: return False
    complete_price = all(project.price_context.get(field) for field in ("tax_inclusion", "price_type", "price_source"))
    if intent.price_source_status == "complete" and not complete_price: return False
    if intent.price_source_status == "incomplete" and complete_price: return False
    comparable = comparability(project)
    if intent.reference_scope == "available" and comparable == "restricted": return False
    if intent.reference_scope == "restricted" and comparable != "restricted": return False
    try:
        unit_price = Decimal(record.unit_price_value or 0) / (Decimal(10) ** record.unit_price_scale)
        if intent.price_min and unit_price < Decimal(intent.price_min): return False
        if intent.price_max and unit_price > Decimal(intent.price_max): return False
    except (InvalidOperation, ValueError):
        return False
    if intent.query and intent.query.lower() not in " ".join(filter(None, [record.name, record.code, record.specification, str(record.payload.get("description") or "")])).lower(): return False
    return True


def search(session: Session, library: LibraryName, intent: Any) -> list[tuple[LibraryRecord, Project, SourceFile | None]]:
    published = session.execute(select(ProjectVersion, Project).join(Project).where(ProjectVersion.status == "published")).all()
    project_by_version = {version.id: project for version, project in published}
    if not project_by_version:
        return []
    with _session_factory(library)() as target:
        rows = target.scalars(select(LibraryRecord).where(LibraryRecord.project_version_id.in_(project_by_version))).all()
    source_ids = {row.source_file_id for row in rows}
    sources = {source.id: source for source in session.scalars(select(SourceFile).where(SourceFile.id.in_(source_ids))).all()} if source_ids else {}
    return [(row, project_by_version[row.project_version_id], sources.get(row.source_file_id)) for row in rows if _allowed(row, project_by_version[row.project_version_id], intent)]


def get_record(library: LibraryName, record_id: str) -> LibraryRecord | None:
    with _session_factory(library)() as target:
        return target.get(LibraryRecord, record_id)


def summaries(session: Session) -> list[dict[str, Any]]:
    published_ids = list(session.scalars(select(ProjectVersion.id).where(ProjectVersion.status == "published")).all())
    result: list[dict[str, Any]] = []
    for library in LIBRARIES:
        path = get_settings().library_paths[library]
        with _session_factory(library)() as target:
            query = select(LibraryRecord).where(LibraryRecord.project_version_id.in_(published_ids)) if published_ids else select(LibraryRecord).where(False)
            rows = target.scalars(query).all()
        status = "ok"
        try:
            with _session_factory(library)() as target:
                healthy = target.execute(select(LibraryRecord.id).limit(1)).first() is not None or True
            if not healthy:
                status = "degraded"
        except Exception:
            status = "degraded"
        result.append({"key": library, "name": LIBRARY_LABELS[library], "database": path.name, "status": status, "record_count": len(rows), "project_count": len({row.project_id for row in rows}), "updated_at": max((row.synced_at for row in rows), default=None)})
    return result
