from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from cost_data import __version__
from cost_data.api import router
from cost_data.backups import apply_pending_restore
from cost_data.config import get_settings
from cost_data.db import init_db


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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
            if origin and origin not in {
                f"http://127.0.0.1:{settings.port}",
                f"http://localhost:{settings.port}",
                "http://127.0.0.1:5173",
                "http://localhost:5173",
            }:
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "INVALID_ORIGIN", "message": "请求来源无效"}},
                )
        return await call_next(request)


def create_app() -> FastAPI:
    apply_pending_restore()
    init_db()
    app = FastAPI(
        title="衡鉴造价库 API",
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
