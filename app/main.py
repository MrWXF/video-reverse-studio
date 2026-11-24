import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from .api.prompt_routes import router as prompt_router
from .api.routes import router
from .config import PROJECT_ROOT, get_settings
from .db import SessionLocal, init_db
from .models import Job, PromptProject
from .security import BasicAuthMiddleware

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
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
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(BasicAuthMiddleware)
app.include_router(router)
app.include_router(prompt_router)
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")),
    name="static",
)
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    mode = (
        "Mock"
        if settings.llm_provider.lower() == "mock" or not settings.llm_api_key
        else settings.llm_provider
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "app_name": settings.app_name, "mode": mode},
    )
