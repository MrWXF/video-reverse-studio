import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import Settings, get_settings
from ..db import get_db
from ..models import Job, Project, PromptProject, Shot
from ..schemas import ShotAnalysis, ShotAnalysisUpdate
from ..serializers import job_payload, project_payload, shot_payload
from ..services import media, pipeline, sse
from ..services.reference import (
    aspect_ratio_for,
    build_reference_context,
    rebuild_project_recipe,
)

router = APIRouter()
ALLOWED_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


def _project_media_path(project_id: str, stored_path: str, settings: Settings) -> Path:
    root = pipeline.project_dir(project_id, settings).resolve()
    path = Path(stored_path)
    if not path.is_absolute():
        path = settings.data_dir / path
    path = path.resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return path


@router.get("/healthz")
def healthz() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_enabled": bool(settings.llm_api_key) and settings.llm_provider.lower() != "mock",
        "ffmpeg": bool(media.resolve_ffmpeg(settings.ffmpeg_bin)),
        "ffprobe": bool(media.resolve_ffprobe(settings.ffprobe_bin)),
    }


@router.post("/api/projects", status_code=201)
def create_project(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400, detail=f"不支持的视频格式：{suffix or '未知'}"
        )

    project_id = str(uuid.uuid4())
    root = settings.data_dir / "projects" / project_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"source{suffix}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0

    try:
        with target.open("wb") as handle:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {settings.max_upload_mb}MB 限制",
                    )
                handle.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    project = Project(
        id=project_id,
        title=title.strip() or Path(file.filename or "未命名").stem,
        source_path=str(target),
        status="queued",
    )
    job = Job(id=str(uuid.uuid4()), project_id=project_id, status="queued", step="queued")
    db.add_all([project, job])
    db.commit()
    background.add_task(pipeline.run_pipeline, project_id, job.id)
    return {"project_id": project_id, "job_id": job.id, "status": "queued"}


@router.get("/api/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.scalars(
        select(Project)
        .options(selectinload(Project.shots))
        .order_by(Project.created_at.desc())
    ).all()
    payload: list[dict] = []
    for project in projects:
        job = db.scalar(
            select(Job)
            .where(Job.project_id == project.id)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        payload.append(project_payload(project, job))
    return payload


@router.get("/api/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.shots))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    job = db.scalar(
        select(Job)
        .where(Job.project_id == project_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    payload = project_payload(project, job, include_shots=True)
    prompt_projects = db.scalars(
        select(PromptProject)
        .where(PromptProject.source_project_id == project_id)
        .order_by(PromptProject.created_at.desc())
    ).all()
    payload["prompt_projects"] = [
        {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "reference_mode": item.reference_mode,
        }
        for item in prompt_projects
    ]
    return payload


@router.get("/api/projects/{project_id}/reference-context")
def get_reference_context(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.shots))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.status != "done" or not project.shots:
        raise HTTPException(status_code=409, detail="项目尚未完成分析")
    context = build_reference_context(project)
    recipe = context.recipe
    return {
        "reference": context.model_dump(mode="json"),
        "suggested": {
            "title": f"{recipe.title} · 新方案",
            "duration_s": round(recipe.duration, 1),
            "aspect_ratio": aspect_ratio_for(recipe.width, recipe.height),
            "shot_count": min(max(len(recipe.shots), 1), 8),
            "style": next(
                (shot.visual_style for shot in recipe.shots if shot.visual_style), ""
            ),
            "mood": recipe.summary,
        },
    }


@router.get("/api/projects/{project_id}/video")
def get_project_video(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    path = _project_media_path(project_id, project.source_path, get_settings())
    return FileResponse(path)


@router.get("/api/projects/{project_id}/shots/{shot_id}/keyframe")
def get_shot_keyframe(project_id: str, shot_id: int, db: Session = Depends(get_db)):
    shot = db.scalar(
        select(Shot).where(Shot.id == shot_id, Shot.project_id == project_id)
    )
    if shot is None or not shot.keyframe_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = _project_media_path(project_id, shot.keyframe_path, get_settings())
    return FileResponse(path)


@router.patch("/api/projects/{project_id}/shots/{shot_id}")
def update_shot_analysis(
    project_id: str,
    shot_id: int,
    update: ShotAnalysisUpdate,
    db: Session = Depends(get_db),
) -> dict:
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.shots))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="项目正在分析，暂时不能编辑")
    shot = next((item for item in project.shots if item.id == shot_id), None)
    if shot is None:
        raise HTTPException(status_code=404, detail="镜头不存在")

    changes = update.model_dump(exclude_unset=True)
    transcript = changes.pop("transcript", None)
    analysis = ShotAnalysis.model_validate({**(shot.analysis or {}), **changes})
    shot.analysis = analysis.model_dump(mode="json")
    shot.origin = analysis.origin
    shot.confidence = analysis.confidence
    if transcript is not None:
        shot.transcript = transcript
    project.status = "done"
    db.commit()
    rebuild_project_recipe(project, get_settings())
    return shot_payload(shot)


@router.post("/api/projects/{project_id}/analyze", status_code=202)
def reanalyze(
    project_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    active = db.scalar(
        select(Job).where(
            Job.project_id == project_id,
            Job.status.in_(["queued", "running"]),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="该项目已有分析任务在进行")
    job = Job(id=str(uuid.uuid4()), project_id=project_id, status="queued", step="queued")
    project.status = "queued"
    db.add(job)
    db.commit()
    background.add_task(pipeline.run_pipeline, project_id, job.id)
    return {"job_id": job.id, "status": "queued"}


@router.get("/api/projects/{project_id}/recipe")
def get_recipe(
    project_id: str,
    format: str = "md",
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    output_dir = pipeline.project_dir(project_id, get_settings()) / "output"

    if format.lower() == "json":
        path = output_dir / "video.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="配方尚未生成")
        return JSONResponse(
            content=json.loads(path.read_text(encoding="utf-8")),
            headers={"Content-Disposition": f'attachment; filename="{project_id}.json"'},
        )

    path = output_dir / "video.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="配方尚未生成")
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{project_id}.md"'},
    )


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_payload(job) or {}


@router.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, request: Request, db: Session = Depends(get_db)):
    if db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StreamingResponse(
        sse.job_event_stream(request, job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/projects/{project_id}/cancel", status_code=202)
def cancel_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    job = db.scalar(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.status.in_(["queued", "running"]),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    if job is None:
        raise HTTPException(status_code=409, detail="该项目没有可取消的任务")
    job.status = "cancelled"
    job.step = "cancelled"
    job.error = "用户已取消任务"
    job.updated_at = datetime.now(timezone.utc)
    project.status = "cancelled"
    db.commit()
    return {"project_id": project_id, "job_id": job.id, "status": "cancelled"}


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.delete(project)
    db.commit()

    settings = get_settings()
    root = pipeline.project_dir(project_id, settings).resolve()
    projects_root = (settings.data_dir / "projects").resolve()
    if root.exists() and projects_root in root.parents:
        shutil.rmtree(root, ignore_errors=True)
    return {"deleted": project_id}
