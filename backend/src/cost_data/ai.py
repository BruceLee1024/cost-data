from __future__ import annotations

import json
import os
import time
from typing import Any, TypeVar

import httpx
import keyring
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from cost_data.config import get_settings
from cost_data.models import AICall, AIConsent, AppSetting
from cost_data.schemas import AISuggestion, CandidateReviewRequest, SearchIntent


T = TypeVar("T", bound=BaseModel)
KEYRING_SERVICE = "cost-data"
KEYRING_ACCOUNT = "deepseek-api-key"


def redact_payload(payload: Any) -> Any:
    sensitive_keys = {"project_name", "client", "建设单位", "客户", "api_key"}
    if isinstance(payload, dict):
        return {
            key: "***" if key.lower() in sensitive_keys else redact_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload


def get_api_key() -> str | None:
    try:
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    except keyring.errors.KeyringError:
        value = None
    return value or os.getenv("DEEPSEEK_API_KEY")


def set_api_key(value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, value)


def get_ai_configuration(session: Session) -> tuple[str, str]:
    settings = get_settings()
    stored = session.get(AppSetting, "ai")
    if not stored:
        return settings.deepseek_base_url, settings.deepseek_model
    return stored.value.get("base_url", settings.deepseek_base_url), stored.value.get("model", settings.deepseek_model)


def set_ai_configuration(session: Session, base_url: str, model: str) -> None:
    stored = session.get(AppSetting, "ai")
    if stored:
        stored.value = {"base_url": base_url, "model": model}
    else:
        session.add(AppSetting(key="ai", value={"base_url": base_url, "model": model}))


def require_consent(session: Session, capability: str) -> None:
    consent = session.scalar(select(AIConsent).where(AIConsent.capability == capability))
    if not consent or not consent.approved:
        raise PermissionError("该 AI 功能尚未获得数据外发授权")


def call_structured(
    session: Session,
    capability: str,
    messages: list[dict[str, str]],
    response_model: type[T],
    request_payload: dict[str, Any],
) -> T:
    require_consent(session, capability)
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("尚未配置 DeepSeek API Key")
    base_url, model = get_ai_configuration(session)
    redacted = redact_payload(request_payload)
    started = time.perf_counter()
    call = AICall(
        capability=capability,
        provider="deepseek",
        model=model,
        prompt_version="v1",
        request_payload=redacted,
        status="running",
    )
    session.add(call)
    session.commit()
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
                timeout=get_settings().ai_request_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("模型返回空内容")
            parsed = response_model.model_validate(json.loads(content))
            call.status = "success"
            call.response_payload = redact_payload(parsed.model_dump(mode="json"))
            call.latency_ms = round((time.perf_counter() - started) * 1000)
            session.commit()
            return parsed
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
    call.status = "failed"
    call.error = str(last_error)
    call.latency_ms = round((time.perf_counter() - started) * 1000)
    session.commit()
    raise RuntimeError(f"DeepSeek 结构化输出失败：{last_error}")


def parse_search_intent(session: Session, text: str) -> SearchIntent:
    messages = [
        {
            "role": "system",
            "content": (
                "你是工程造价数据查询解析器。只输出 JSON。将用户问题转换为筛选条件，"
                "不得生成 SQL，不得编造缺失条件。字段包括 query, region, pricing_date_from, "
                "pricing_date_to, specialty, project_type, pricing_mode, result_stage, unit, code, "
                "specification, price_min, price_max, limit。limit 固定为 50。"
            ),
        },
        {"role": "user", "content": text},
    ]
    return call_structured(
        session,
        "search_intent",
        messages,
        SearchIntent,
        {"text": text},
    )


def review_candidates(session: Session, payload: CandidateReviewRequest) -> AISuggestion:
    request_data = payload.model_dump(mode="json")
    messages = [
        {
            "role": "system",
            "content": (
                "你是工程造价候选匹配复核助手。只依据提供的清单项、候选和确定性评分输出 JSON。"
                "不得修改数据、不得计算价格、不得虚构口径。输出 suggestion、uncertainties、"
                "confidence_reason、recommended_candidate_id、confirmation_status；确认状态固定 pending。"
            ),
        },
        {"role": "user", "content": json.dumps(request_data, ensure_ascii=False)},
    ]
    suggestion = call_structured(
        session, "candidate_review", messages, AISuggestion, request_data
    )
    _base_url, model = get_ai_configuration(session)
    return suggestion.model_copy(update={"model": model, "prompt_version": "v1"})
