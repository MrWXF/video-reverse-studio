"""HTTP endpoints for video upload, analysis, timeline editing, and media delivery."""

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
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import Settings, get_settings
from ..db import get_db
from ..models import Job, Project, PromptProject, Shot, ShotEditEvent
from ..observability import current_request_id
from ..schemas import (
    ShotAnalysis,
    ShotAnalysisUpdate,
    TimelineBoundaryUpdate,
    TimelineMergeRequest,
    TimelineSplitRequest,
)
from ..serializers import job_payload, project_payload, shot_payload
from ..services import capacity, media, pipeline, sse, timeline, uploads
from ..services.http_range import range_file_response
from ..services.reference import (
    aspect_ratio_for,
    build_reference_context,
    rebuild_project_recipe,
)

router = APIRouter()
ALLOWED_SUFFIXES = uploads.VIDEO_SUFFIXES


def _project_media_path(project_id: str, stored_path: str, settings: Settings) -> Path:
    """Resolve a stored path and reject files outside the project's media directory."""
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
    """Return service readiness, provider configuration, media tools, and job capacity."""
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_enabled": bool(settings.llm_api_key) and settings.llm_provider.lower() != "mock",
        "ffmpeg": bool(media.resolve_ffmpeg(settings.ffmpeg_bin)),
        "ffprobe": bool(media.resolve_ffprobe(settings.ffprobe_bin)),
        "api_version": "v1",
        "active_jobs": capacity.active_jobs(),
    }


@router.post(
    "/api/projects",
    status_code=201,
    summary="创建视频逆向项目",
    description=(
        "上传视频并启动分镜检测、关键帧抽取和逐镜分析。"
        "支持 MP4、MOV、WebM、MKV、AVI、M4V，服务端会校验文件头。"
    ),
    responses={
        201: {"description": "项目与分析任务已创建"},
        400: {"description": "格式或文件内容不合法"},
        413: {"description": "文件超过大小限制"},
        503: {"description": "当前并发任务已达上限"},
    },
)
def create_project(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
) -> dict:
    """Validate and persist an upload, then queue the full analysis pipeline."""
    settings = get_settings()
    if not capacity.has_capacity(settings.max_active_jobs):
        raise HTTPException(status_code=503, detail="当前分析任务已达并发上限，请稍后重试")

    original_name = uploads.safe_filename(file.filename or "")
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400, detail=f"不支持的视频格式：{suffix or '未知'}"
        )

    project_id = str(uuid.uuid4())
    root = settings.data_dir / "projects" / project_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"source{suffix}"
    limit = settings.max_upload_mb * 1024 * 1024

    try:
        uploads.save_validated_upload(file, target, limit)
    except uploads.UploadTooLargeError as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {settings.max_upload_mb}MB 限制",
        ) from exc
    except uploads.UploadValidationError as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    project = Project(
        id=project_id,
        title=uploads.clean_text(
            title,
            default=Path(original_name).stem or "未命名项目",
            limit=200,
        ),
        source_path=str(target),
        status="queued",
    )
    job = Job(id=str(uuid.uuid4()), project_id=project_id, status="queued", step="queued")
    db.add_all([project, job])
    db.commit()
    background.add_task(
        pipeline.run_pipeline,
        project_id,
        job.id,
        request_id=current_request_id(),
    )
    return {"project_id": project_id, "job_id": job.id, "status": "queued"}


@router.get("/api/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    """List projects newest-first with their latest job summary and shot data."""
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
        payload.append(
            project_payload(
                project,
                job,
                timeline_min_shot_seconds=get_settings().min_shot_seconds,
            )
        )
    return payload


@router.get("/api/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    """Return a project, its shots, and prompt projects linked to this analysis."""
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
    payload = project_payload(
        project,
        job,
        include_shots=True,
        timeline_min_shot_seconds=get_settings().min_shot_seconds,
    )
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
    """Return reusable reference context plus suggested prompt-project defaults."""
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
def get_project_video(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Stream the source video with byte-range support for browser seeking."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    path = _project_media_path(project_id, project.source_path, get_settings())
    return range_file_response(path, request)


@router.get("/api/projects/{project_id}/shots/{shot_id}/keyframe")
def get_shot_keyframe(
    project_id: str,
    shot_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Stream a shot keyframe with byte-range support."""
    shot = db.scalar(
        select(Shot).where(Shot.id == shot_id, Shot.project_id == project_id)
    )
    if shot is None or not shot.keyframe_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = _project_media_path(project_id, shot.keyframe_path, get_settings())
    return range_file_response(path, request)


@router.patch("/api/projects/{project_id}/shots/{shot_id}")
def update_shot_analysis(
    project_id: str,
    shot_id: int,
    update: ShotAnalysisUpdate,
    db: Session = Depends(get_db),
) -> dict:
    """Apply manual shot edits, record changed fields, and rebuild the project recipe.

    Editing is rejected while the project has an active analysis job. The
    database commit happens before the derived recipe is rebuilt.
    """
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
    before = ShotAnalysis.model_validate(shot.analysis or {}).model_dump(mode="json")
    analysis = ShotAnalysis.model_validate({**before, **changes})
    after = analysis.model_dump(mode="json")
    changed_fields = {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in changes
        if before.get(field) != after.get(field)
    }
    if transcript is not None and shot.transcript != transcript:
        changed_fields["transcript"] = {
            "before": shot.transcript,
            "after": transcript,
        }
    shot.analysis = after
    shot.origin = analysis.origin
    shot.confidence = analysis.confidence
    if transcript is not None:
        shot.transcript = transcript
    if changed_fields:
        db.add(
            ShotEditEvent(
                project_id=project.id,
                shot_id=shot.id,
                shot_index=shot.index,
                source="manual_edit",
                changes=changed_fields,
            )
        )
    project.status = "done"
    db.commit()
    rebuild_project_recipe(project, get_settings())
    return shot_payload(shot)


def _timeline_response(mutation: timeline.TimelineMutation) -> dict:
    """Serialize a queued timeline mutation for the HTTP response."""
    return {
        "job_id": mutation.job_id,
        "status": "queued",
        "action": mutation.action,
        "affected_shot_ids": mutation.affected_shot_ids,
        "prompt_projects_invalidated": mutation.prompt_projects_invalidated,
    }


def _timeline_error(exc: timeline.TimelineError) -> HTTPException:
    """Map timeline domain errors to their public HTTP status codes."""
    if isinstance(exc, timeline.TimelineNotFoundError):
        status_code = 404
    elif isinstance(exc, timeline.TimelineConflictError):
        status_code = 409
    elif isinstance(exc, timeline.TimelineCapacityError):
        status_code = 503
    else:
        status_code = 422
    return HTTPException(status_code=status_code, detail=str(exc))


def _timeline_project(db: Session, project_id: str) -> Project:
    """Load a project or raise a 404 for timeline endpoints."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.patch(
    "/api/projects/{project_id}/shots/{shot_id}/boundary",
    status_code=202,
    summary="调整相邻镜头边界",
)
def update_timeline_boundary(
    project_id: str,
    shot_id: int,
    payload: TimelineBoundaryUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Move a boundary between adjacent shots and queue targeted re-analysis.

    The service commits the timeline mutation and queues a job before the
    background task starts. Linked prompt projects are warned that their
    reference mapping may have changed.
    """
    project = _timeline_project(db, project_id)
    settings = get_settings()
    try:
        mutation = timeline.update_boundary(
            db, project, shot_id, payload.boundary_s, settings
        )
    except timeline.TimelineError as exc:
        db.rollback()
        raise _timeline_error(exc) from exc
    background.add_task(
        timeline.run_timeline_reanalysis,
        project_id,
        mutation.job_id,
        mutation.affected_shot_ids,
    )
    return _timeline_response(mutation)


@router.post(
    "/api/projects/{project_id}/shots/{shot_id}/split",
    status_code=202,
    summary="拆分镜头",
)
def split_timeline_shot(
    project_id: str,
    shot_id: int,
    payload: TimelineSplitRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Split one shot at a validated timestamp and queue targeted re-analysis."""
    project = _timeline_project(db, project_id)
    settings = get_settings()
    try:
        mutation = timeline.split_shot(
            db, project, shot_id, payload.split_at, settings
        )
    except timeline.TimelineError as exc:
        db.rollback()
        raise _timeline_error(exc) from exc
    background.add_task(
        timeline.run_timeline_reanalysis,
        project_id,
        mutation.job_id,
        mutation.affected_shot_ids,
    )
    return _timeline_response(mutation)


@router.post(
    "/api/projects/{project_id}/shots/merge",
    status_code=202,
    summary="合并相邻镜头",
)
def merge_timeline_shots(
    project_id: str,
    payload: TimelineMergeRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Merge two adjacent shots and queue re-analysis for the merged shot."""
    project = _timeline_project(db, project_id)
    settings = get_settings()
    try:
        mutation = timeline.merge_shots(
            db, project, payload.shot_ids, settings
        )
    except timeline.TimelineError as exc:
        db.rollback()
        raise _timeline_error(exc) from exc
    background.add_task(
        timeline.run_timeline_reanalysis,
        project_id,
        mutation.job_id,
        mutation.affected_shot_ids,
    )
    return _timeline_response(mutation)


@router.post(
    "/api/projects/{project_id}/shots/{shot_id}/reanalyze",
    status_code=202,
    summary="重抽关键帧并重新分析镜头",
)
def reanalyze_timeline_shot(
    project_id: str,
    shot_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Queue keyframe extraction and analysis for one existing shot."""
    project = _timeline_project(db, project_id)
    settings = get_settings()
    try:
        mutation = timeline.queue_reanalysis(db, project, shot_id, settings)
    except timeline.TimelineError as exc:
        db.rollback()
        raise _timeline_error(exc) from exc
    background.add_task(
        timeline.run_timeline_reanalysis,
        project_id,
        mutation.job_id,
        mutation.affected_shot_ids,
    )
    return _timeline_response(mutation)


@router.post(
    "/api/projects/{project_id}/analyze",
    status_code=202,
    summary="重新分析项目",
    responses={202: {"description": "任务已排队"}, 409: {"description": "已有任务进行中"}},
)
def reanalyze(
    project_id: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Queue a full analysis when no project job is active and capacity is available."""
    settings = get_settings()
    if not capacity.has_capacity(settings.max_active_jobs):
        raise HTTPException(status_code=503, detail="当前分析任务已达并发上限，请稍后重试")
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
    background.add_task(
        pipeline.run_pipeline,
        project_id,
        job.id,
        request_id=current_request_id(),
    )
    return {"job_id": job.id, "status": "queued"}


@router.get("/api/projects/{project_id}/recipe")
def get_recipe(
    project_id: str,
    format: str = "md",
    db: Session = Depends(get_db),
):
    """Download the generated recipe as Markdown or JSON."""
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
    """Return the current status, progress, and metrics for one job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_payload(job) or {}


@router.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, request: Request, db: Session = Depends(get_db)):
    """Stream job status changes as server-sent events."""
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
    """Mark the active project job cancelled and mirror that state on the project."""
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
    """Delete a project record and its managed media directory.

    The filesystem removal is restricted to the configured projects root and
    happens only after the database deletion succeeds.
    """
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
