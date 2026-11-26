"""FastAPI application assembly, middleware, lifespan hooks, and HTML entry points."""

import logging
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from .api.generation_routes import router as generation_router
from .api.insight_routes import router as insight_router
from .api.prompt_routes import router as prompt_router
from .api.routes import router
from .api.share_routes import router as share_router
from .config import PROJECT_ROOT, get_settings
from .db import SessionLocal, init_db
from .models import GenerationJob, Job, PromptProject
from .observability import (
    RequestContextMiddleware,
    configure_logging,
    current_request_id,
)
from .security import BasicAuthMiddleware
from .services.redaction import redact_exception

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize storage and fail jobs that were interrupted by a restart."""
    init_db()
    with SessionLocal() as db:
        stale = db.scalars(
            select(Job).where(Job.status.in_(["queued", "running"]))
        ).all()
        for job in stale:
            job.status = "failed"
            job.error = "服务重启导致任务中断，请重新分析"
            job.updated_at = datetime.now(timezone.utc)
        if stale:
            db.commit()
            logger.warning("marked %s stale jobs as failed", len(stale))
        stale_prompts = db.scalars(
            select(PromptProject).where(
                PromptProject.status.in_(["queued", "running"])
            )
        ).all()
        for project in stale_prompts:
            project.status = "failed"
            project.step = "failed"
            project.error = "服务重启导致生成任务中断，请重新生成"
            project.updated_at = datetime.now(timezone.utc)
        if stale_prompts:
            db.commit()
            logger.warning(
                "marked %s stale prompt projects as failed", len(stale_prompts)
            )
        stale_generations = db.scalars(
            select(GenerationJob).where(
                GenerationJob.status.in_(["queued", "running"])
            )
        ).all()
        for job in stale_generations:
            job.status = "failed"
            job.step = "failed"
            job.error = "服务重启导致视频生成任务中断，请重新生成"
            job.updated_at = datetime.now(timezone.utc)
        if stale_generations:
            db.commit()
            logger.warning(
                "marked %s stale generation jobs as failed", len(stale_generations)
            )
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
    description=(
        "视频逆向与提示词生成工作台。`/api` 为兼容入口，`/api/v1` 为正式版本入口；"
        "两个入口共享同一套 v1 语义。"
    ),
)
app.add_middleware(BasicAuthMiddleware)
app.add_middleware(RequestContextMiddleware)
app.include_router(router, tags=["video-analysis"])
app.include_router(prompt_router, tags=["prompt-studio"])
app.include_router(insight_router, tags=["phase1-insights"])
app.include_router(generation_router, tags=["video-generation"])
app.include_router(share_router)
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")),
    name="static",
)
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


def custom_openapi() -> dict:
    """Expose the same v1 operations under both /api and /api/v1 in docs."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    paths = dict(schema.get("paths", {}))
    for path, operations in list(paths.items()):
        if not path.startswith("/api/"):
            continue
        versioned_path = "/api/v1" + path[len("/api") :]
        versioned = deepcopy(operations)
        for operation in versioned.values():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id:
                operation["operationId"] = f"{operation_id}_v1"
            operation["tags"] = ["API v1"]
        paths[versioned_path] = versioned
    schema["paths"] = paths
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a redacted 500 response while retaining full details in server logs."""
    logger.exception("unhandled request error path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "request_id": current_request_id(),
            "error": redact_exception(exc, settings, limit=500),
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Render the main workspace shell with the active provider label."""
    mode = (
        "Mock"
        if settings.llm_provider.lower() == "mock" or not settings.llm_api_key
        else settings.llm_provider
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "app_name": settings.app_name, "mode": mode},
    )
