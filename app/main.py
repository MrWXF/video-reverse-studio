"""FastAPI application assembly, middleware, lifespan hooks, and HTML entry points."""

import logging
from contextlib import asynccontextmanager
from copy import deepcopy

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api.generation_routes import router as generation_router
from .api.insight_routes import router as insight_router
from .api.prompt_routes import router as prompt_router
from .api.routes import router
from .api.share_routes import router as share_router
from .config import PROJECT_ROOT, get_settings
from .db import init_db
from .observability import (
    RequestContextMiddleware,
    configure_logging,
    current_request_id,
)
from .request_limits import RequestBodyLimitMiddleware
from .security import BasicAuthMiddleware
from .services import task_queue
from .services.redaction import redact_exception

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize storage, recover durable tasks, and run the dispatcher."""
    init_db()
    task_queue.start_dispatcher()
    try:
        yield
    finally:
        task_queue.stop_dispatcher()


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
    description=(
        "视频逆向与提示词生成工作台。`/api` 为兼容入口，`/api/v1` 为正式版本入口；"
        "两个入口共享同一套 v1 语义。"
    ),
    # ``/docs`` is a hand-written reference page; the OpenAPI schema stays
    # available at ``/openapi.json`` for tooling and code generation.
    docs_url=None,
    redoc_url=None,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(BasicAuthMiddleware)
app.add_middleware(RequestBodyLimitMiddleware)
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
react_index = PROJECT_ROOT / "app" / "static" / "react" / "index.html"
docs_index = PROJECT_ROOT / "app" / "static" / "docs" / "index.html"


@app.get("/docs", include_in_schema=False)
def api_docs():
    """Serve the hand-written API reference instead of the Swagger UI."""
    return FileResponse(docs_index)


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
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["BasicAuth"] = {
        "type": "http",
        "scheme": "basic",
        "description": "配置 APP_PASSWORD 后，业务接口需要 HTTP Basic 认证。",
    }
    for path, operations in paths.items():
        public = (
            path == "/healthz"
            or path.startswith("/share/")
            or path.startswith("/api/shares/")
            or path.startswith("/api/v1/shares/")
        )
        if public:
            continue
        for operation in operations.values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{"BasicAuth": []}])
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


@app.get("/app", include_in_schema=False)
@app.get("/app/{path:path}", include_in_schema=False)
def react_frontend(path: str = ""):
    """Serve the built React application while the legacy screen remains at ``/``.

    The SPA entry point is available only after ``npm run build`` has produced
    ``app/static/react/index.html``. Returning a clear 404 keeps local setup
    failures easier to diagnose than silently falling back to the old page.
    """
    del path
    if not react_index.is_file():
        raise HTTPException(
            status_code=404,
            detail="React 前端尚未构建，请在 web 目录执行 npm run build",
        )
    return FileResponse(react_index)
