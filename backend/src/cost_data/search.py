from __future__ import annotations

import statistics
from decimal import Decimal

from rapidfuzz.fuzz import ratio, token_set_ratio
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from cost_data.fixedpoint import from_scaled, to_scaled
from cost_data.models import CostItem, MatchSession, Project, ProjectVersion, SourceFile
from cost_data.normalization import apply_synonyms, normalize_text, normalize_unit, specification_tokens
from cost_data.schemas import (
    ComparisonRead,
    CostComponentRead,
    CostItemRead,
    DecimalValue,
    MatchCandidate,
    MatchQueryItem,
    MatchQueryResult,
    MatchSessionRead,
    ScorePart,
    SearchIntent,
    SearchResult,
    SourceRef,
)


def decimal_value(value: int | None, scale: int, *, unit: str | None = None, currency: str | None = None) -> DecimalValue:
    return DecimalValue(value=from_scaled(value, scale), scale=scale, unit=unit, currency=currency)


def source_ref(item: CostItem, source_file: SourceFile) -> SourceRef:
    return SourceRef(
        file_id=source_file.id,
        file_name=source_file.original_name,
        sheet_name=item.sheet_name,
        start_row=item.source_row,
        end_row=item.source_end_row,
        cell_range=f"{item.source_row}:{item.source_end_row or item.source_row}",
    )


def serialize_cost_item(item: CostItem, project: Project, source_file: SourceFile) -> CostItemRead:
    components = [
        CostComponentRead(
            id=component.id,
            category=component.category,
            name=component.name,
            amount=decimal_value(component.value, component.scale, currency=item.currency),
            source=SourceRef(
                file_id=component.source_file_id,
                file_name=source_file.original_name,
                sheet_name=component.sheet_name,
                start_row=component.source_row,
                cell_range=str(component.source_row),
            ),
        )
        for component in item.components
    ]
    return CostItemRead(
        id=item.id,
        project_id=project.id,
        project_name=project.name,
        project_version_id=item.project_version_id,
        code=item.code,
        name=item.name,
        normalized_name=item.normalized_name,
        description=item.description,
        specification=item.specification,
        unit=item.unit,
        quantity=decimal_value(item.quantity_value, item.quantity_scale, unit=item.unit),
        unit_price=decimal_value(item.unit_price_value, item.unit_price_scale, currency=item.currency),
        total=decimal_value(item.total_value, item.total_scale, currency=item.currency),
        region=project.region,
        pricing_date=project.pricing_date,
        specialty=project.specialty,
        pricing_mode=project.pricing_mode,
        result_stage=project.result_stage,
        source=source_ref(item, source_file),
        components=components,
    )


def _base_query():
    return (
        select(CostItem, Project, SourceFile)
        .join(ProjectVersion, ProjectVersion.id == CostItem.project_version_id)
        .join(Project, Project.id == ProjectVersion.project_id)
        .join(SourceFile, SourceFile.id == CostItem.source_file_id)
        .where(ProjectVersion.status == "published", CostItem.status == "active")
        .options(selectinload(CostItem.components))
    )


def _apply_filters(statement, intent: SearchIntent):  # type: ignore[no-untyped-def]
    if intent.region:
        statement = statement.where(Project.region == intent.region)
    if intent.specialty:
        statement = statement.where(Project.specialty == intent.specialty)
    if intent.project_type:
        statement = statement.where(Project.project_type == intent.project_type)
    if intent.pricing_mode:
        statement = statement.where(Project.pricing_mode == intent.pricing_mode)
    if intent.result_stage:
        statement = statement.where(Project.result_stage == intent.result_stage)
    if intent.pricing_date_from:
        statement = statement.where(Project.pricing_date >= intent.pricing_date_from)
    if intent.pricing_date_to:
        statement = statement.where(Project.pricing_date <= intent.pricing_date_to)
    if intent.unit:
        statement = statement.where(CostItem.unit == normalize_unit(intent.unit))
    if intent.code:
        statement = statement.where(CostItem.code.like(f"{intent.code}%"))
    if intent.specification:
        statement = statement.where(CostItem.specification.like(f"%{intent.specification}%"))
    if intent.price_min:
        statement = statement.where(CostItem.unit_price_value >= to_scaled(intent.price_min))
    if intent.price_max:
        statement = statement.where(CostItem.unit_price_value <= to_scaled(intent.price_max))
    if intent.query:
        clean = normalize_text(intent.query)
        if len(clean) >= 3:
            fts_query = f'"{clean.replace(chr(34), chr(34) * 2)}"'
            statement = statement.where(
                CostItem.id.in_(
                    select(text("cost_item_id")).select_from(text("cost_item_fts")).where(
                        text("cost_item_fts MATCH :fts_query")
                    )
                )
            ).params(fts_query=fts_query)
        else:
            pattern = f"%{clean}%"
            statement = statement.where(
                or_(
                    CostItem.name.like(pattern),
                    CostItem.code.like(pattern),
                    CostItem.description.like(pattern),
                    CostItem.specification.like(pattern),
                )
            )
    return statement


def search_cost_items(session: Session, intent: SearchIntent) -> SearchResult:
    statement = _apply_filters(_base_query(), intent)
    total_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = session.scalar(total_statement) or 0
    if intent.cursor:
        statement = statement.where(CostItem.id > intent.cursor)
    rows = session.execute(statement.order_by(CostItem.id).limit(intent.limit + 1)).unique().all()
    has_more = len(rows) > intent.limit
    rows = rows[: intent.limit]
    items = [serialize_cost_item(item, project, source) for item, project, source in rows]
    return SearchResult(
        items=items,
        next_cursor=items[-1].id if has_more and items else None,
        total=total,
    )


def get_cost_item(session: Session, item_id: str) -> CostItemRead | None:
    row = session.execute(_base_query().where(CostItem.id == item_id)).unique().one_or_none()
    if not row:
        return None
    return serialize_cost_item(*row)


def compare_cost_items(session: Session, item_ids: list[str]) -> ComparisonRead:
    rows = session.execute(_base_query().where(CostItem.id.in_(item_ids))).unique().all()
    items = [serialize_cost_item(item, project, source) for item, project, source in rows]
    prices = [Decimal(item.unit_price.value) for item in items if item.unit_price.value is not None]
    warnings: list[str] = []
    units = {item.unit for item in items}
    modes = {item.pricing_mode for item in items}
    if len(units) > 1:
        warnings.append("样本包含不同计量单位，价格不可直接比较")
    if len(modes) > 1:
        warnings.append("样本包含不同计价体系，请核对口径")
    if not prices:
        empty = decimal_value(None, 6, currency="CNY")
        return ComparisonRead(items=items, sample_count=0, min_price=empty, median_price=empty, max_price=empty, warnings=warnings)
    return ComparisonRead(
        items=items,
        sample_count=len(prices),
        min_price=DecimalValue(value=str(min(prices)), scale=6, currency="CNY"),
        median_price=DecimalValue(value=str(statistics.median(prices)), scale=6, currency="CNY"),
        max_price=DecimalValue(value=str(max(prices)), scale=6, currency="CNY"),
        warnings=warnings,
    )


def rank_candidates(session: Session, query: MatchQueryItem, limit: int = 5) -> list[MatchCandidate]:
    intent = SearchIntent(
        query=query.name,
        code=query.code,
        unit=query.unit,
        specialty=query.specialty,
        limit=50,
    )
    result = search_cost_items(session, intent)
    if not result.items:
        # FTS phrase recall is intentionally precise; fuzzy scoring needs a
        # bounded fallback set when wording differs (for example, omitted specs).
        result = search_cost_items(
            session,
            SearchIntent(unit=query.unit, specialty=query.specialty, limit=200),
        )
    query_name = apply_synonyms(query.name, session)
    query_spec = specification_tokens(query.specification)
    query_unit = normalize_unit(query.unit, session)
    candidates: list[MatchCandidate] = []
    for item in result.items:
        exclusions: list[str] = []
        parts: list[ScorePart] = []
        candidate_unit = normalize_unit(item.unit, session)
        if query_unit and candidate_unit and query_unit != candidate_unit:
            exclusions.append(f"单位不兼容：{query_unit} / {candidate_unit}")
        code_score = 0
        if query.code and item.code:
            code_score = 35 if query.code == item.code else 20 if item.code.startswith(query.code) else 0
        parts.append(ScorePart(label="编码", score=code_score, reason="编码一致" if code_score == 35 else "编码前缀或未命中"))
        name_score = round(ratio(query_name, apply_synonyms(item.name, session)) * 0.35)
        description_score = round(token_set_ratio(query_name, normalize_text(item.description or item.name)) * 0.15)
        parts.append(ScorePart(label="名称", score=name_score, reason=f"名称相似度 {name_score / 35:.0%}"))
        parts.append(ScorePart(label="描述", score=description_score, reason="项目特征词匹配"))
        candidate_spec = specification_tokens(item.specification)
        spec_score = 0
        if query_spec:
            spec_score = round(len(query_spec & candidate_spec) / len(query_spec) * 10)
        parts.append(ScorePart(label="规格", score=spec_score, reason=f"关键规格命中 {len(query_spec & candidate_spec)}/{len(query_spec) or 0}"))
        unit_score = 5 if query_unit and query_unit == candidate_unit else 0
        parts.append(ScorePart(label="单位", score=unit_score, reason="单位一致" if unit_score else "未确认单位"))
        total_score = sum(part.score for part in parts)
        if exclusions:
            total_score = 0
        candidates.append(
            MatchCandidate(cost_item=item, total_score=total_score, score_parts=parts, exclusions=exclusions)
        )
    return sorted(candidates, key=lambda candidate: candidate.total_score, reverse=True)[:limit]


def serialize_match_session(session: Session, match_session: MatchSession) -> MatchSessionRead:
    results = []
    for index, raw_query in enumerate(match_session.query_items):
        query = MatchQueryItem.model_validate(raw_query)
        results.append(
            MatchQueryResult(query_index=index, query=query, candidates=rank_candidates(session, query))
        )
    return MatchSessionRead(
        id=match_session.id,
        name=match_session.name,
        status=match_session.status,
        created_at=match_session.created_at,
        results=results,
    )
