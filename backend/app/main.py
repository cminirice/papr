from contextlib import asynccontextmanager
import sqlite3
from uuid import uuid4
from sqlalchemy.exc import OperationalError
from app.core.config import Settings
from app.core.database import make_engine
from app.core.errors import ServiceError
from app.api.public.session import router as user_session_router
from app.api.admin.session import router as admin_session_router
from app.api.admin.content import router as admin_content_router
from app.api.admin.validation import router as admin_validation_router
from app.api.admin.releases import router as admin_release_router
from app.api.admin.capabilities import router as admin_capability_router
from app.api.admin.operations import router as admin_operations_router
from app.api.admin.catalog_edit import router as admin_catalog_edit_router
from app.api.admin.knowledge_edit import router as admin_knowledge_edit_router
from app.api.admin.audit import router as admin_audit_router
from app.api.admin.settings import router as admin_settings_router
from app.api.admin.papers import router as admin_papers_router
from app.api.admin.template_tools import router as admin_template_tools_router
from app.api.public.catalog import router as public_catalog_router
from app.api.public.jobs import router as paper_jobs_router
from app.api.public.events import router as events_router
from app.api.public.papers import router as papers_router
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse
from app.core.time import beijing_now
from app.schemas.common import Envelope, Health, ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.db_path)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="纸上练", version="0.1.0", lifespan=lifespan,
        responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 415, 422, 429, 500, 503)},
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.clock = beijing_now
    from app.v2.api import admin as v2_admin, public as v2_public
    app.include_router(v2_admin)
    app.include_router(v2_public)
    app.include_router(user_session_router)
    app.include_router(admin_session_router)
    app.include_router(admin_content_router)
    app.include_router(admin_validation_router)
    app.include_router(admin_release_router)
    app.include_router(admin_capability_router)
    app.include_router(admin_operations_router)
    app.include_router(admin_catalog_edit_router)
    app.include_router(admin_knowledge_edit_router)
    app.include_router(admin_template_tools_router)
    app.include_router(admin_papers_router)
    app.include_router(admin_settings_router)
    app.include_router(admin_audit_router)
    app.include_router(public_catalog_router)
    app.include_router(paper_jobs_router)
    app.include_router(papers_router)
    app.include_router(events_router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid4()
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        if request.url.path.startswith(("/api/v1/", "/admin/api/v1/", "/api/v2/", "/admin/api/v2/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def failure(request: Request, status: int, code: str, message: str, details=None, headers=None):
        request_id = str(getattr(request.state, "request_id", uuid4()))
        return JSONResponse(status_code=status, content={
            "error": {"code": code, "message": message, "details": details or {}},
            "request_id": request_id,
        }, headers={"X-Request-ID": request_id, "Cache-Control": "no-store", **(headers or {})})

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return failure(request, exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError):
        code = (getattr(exc.orig, "sqlite_errorcode", 0) or 0)
        if code & 0xff in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return failure(request, 503, "DATABASE_BUSY", "服务繁忙，请稍后重试", headers={"Retry-After": "1"})
        return failure(request, 503, "SERVICE_NOT_READY", "数据库尚未就绪")

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        # 不回显请求输入，避免将未来登录口令等带入错误响应。
        return failure(request, 422, "INVALID_CONFIG", "请求参数不符合接口约定")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return failure(request, exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "INVALID_CONFIG", "请求不可用")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return failure(request, 500, "INTERNAL_ERROR", "服务暂时不可用")

    @app.get("/api/v1/health", response_model=Envelope[Health])
    def health(request: Request):
        return Envelope(data=Health(server_now=beijing_now()), request_id=request.state.request_id)

    return app


app = create_app()
