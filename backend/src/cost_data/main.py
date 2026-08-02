from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from cost_data import __version__
from cost_data.api import router
from cost_data.backups import apply_pending_restore, create_backup, prune_backups
from cost_data.config import get_settings
from cost_data.db import init_db
from cost_data.db import SessionLocal
from cost_data.libraries import init_libraries, sync_published_versions
from cost_data.logging_setup import configure_logging
from cost_data.models import AppSetting


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _run_automatic_backup() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        stored = session.get(AppSetting, "backup")
        if not stored or not stored.value.get("directory"):
            return
        target = Path(stored.value["directory"]).expanduser()
    today = datetime.now().date().isoformat()
    manifests = list(target.glob("*/manifest.json")) if target.exists() else []
    kinds_today: set[str] = set()
    for manifest_path in manifests:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(payload.get("created_at", "")).startswith(today):
                kinds_today.add(str(payload.get("kind")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    if "daily" not in kinds_today:
        create_backup(target, "daily")
    if datetime.now().weekday() == 0 and "weekly" not in kinds_today:
        create_backup(target, "weekly")
    prune_backups(target, settings.backup_retention_daily, settings.backup_retention_weekly)


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        settings = get_settings()
        if request.method not in SAFE_METHODS:
            token = request.headers.get("X-Cost-Data-Token")
            if token != settings.effective_session_token:
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "INVALID_SESSION", "message": "本地会话令牌无效"}},
                )
            origin = request.headers.get("origin")
            parsed_origin = urlparse(origin) if origin else None
            local_origin = bool(
                parsed_origin
                and parsed_origin.scheme == "http"
                and parsed_origin.hostname in {"127.0.0.1", "localhost"}
            )
            if origin and not local_origin:
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "INVALID_ORIGIN", "message": "请求来源无效"}},
                )
        return await call_next(request)


def create_app() -> FastAPI:
    configure_logging()
    apply_pending_restore()
    init_db()
    init_libraries()
    # Existing installations used one database. Mirror published history on startup
    # so upgrading is automatic and retry-safe.
    with SessionLocal() as session:
        sync_published_versions(session)
    threading.Thread(target=_run_automatic_backup, daemon=True, name="cost-data-backup").start()
    app = FastAPI(
        title="工程造价数据库 API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(LocalSecurityMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR", "message": "请求数据校验失败", "details": json.loads(json.dumps(exc.errors(), default=str))}},
        )

    @app.exception_handler(HTTPException)  # type: ignore[name-defined]
    async def http_error(_request: Request, exc):  # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "REQUEST_ERROR", "message": str(exc.detail)}},
        )

    app.include_router(router)
    if getattr(sys, "frozen", False):
        frontend_dist = Path(getattr(sys, "_MEIPASS")) / "frontend" / "dist"
    else:
        frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
