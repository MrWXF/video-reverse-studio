"""HTTP endpoints for the durable video-generation workflow."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import GenerationJob, PromptProject
from ..observability import current_request_id
from ..schemas import GenerationJobCreate
from ..serializers import generation_job_payload
from ..services import capacity, generation, task_queue
from ..services.generation_adapters import GenerationProviderError

router = APIRouter()


def _get_project(db: Session, project_id: str) -> PromptProject:
    """Load a prompt project or raise a 404 for generation endpoints."""
    project = db.get(PromptProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="提示词项目不存在")
    return project


def _get_job(db: Session, job_id: str) -> GenerationJob:
    """Load a generation job or raise a 404."""
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="视频生成任务不存在")
    return job


@router.get("/api/generation/capabilities")
def generation_capabilities() -> dict:
    """Return the active provider, supported ratios, and generation limits."""
    return generation.capabilities(get_settings())


@router.post(
    "/api/prompt-projects/{project_id}/generation-jobs",
    status_code=202,
    summary="创建视频生成任务",
    description=(
        "从已完成的提示词方案创建视频生成任务。平台由服务端配置决定；"
        "前端不接收或回传第三方 API Key。"
    ),
)
def start_generation(
    project_id: str,
    payload: GenerationJobCreate,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Create or reuse a generation job and queue it for execution.

    Idempotency keys make retries safe. Invalid plans, shots, or providers are
    mapped to 409, 422, and 503 respectively; reused jobs do not enqueue a
    second worker.
    """
    settings = get_settings()
    project = _get_project(db, project_id)
    if not capacity.reserve("generation", settings.max_active_generation_jobs):
        raise HTTPException(status_code=503, detail="当前视频生成任务已达并发上限，请稍后重试")
    handed_off = False
    try:
        job, reused = generation.create_generation_job(db, project, payload, settings)
        if not reused:
            task = task_queue.enqueue(
                db,
                "generation",
                job.id,
                request_id=current_request_id(),
            )
            task_queue.schedule(background, db, task)
        else:
            capacity.release_job("generation")
        handed_off = True
    except generation.GenerationPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except generation.GenerationSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if not handed_off:
            capacity.release_job("generation")
    data = generation_job_payload(job)
    data["reused"] = reused
    return data


@router.get("/api/prompt-projects/{project_id}/generation-jobs")
def list_generation_jobs(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """List up to 50 generation jobs for a prompt project, newest-first."""
    _get_project(db, project_id)
    jobs = db.scalars(
        select(GenerationJob)
        .where(GenerationJob.prompt_project_id == project_id)
        .order_by(GenerationJob.created_at.desc())
        .limit(50)
    ).all()
    return [generation_job_payload(job) for job in jobs]


@router.get("/api/generation-jobs/{job_id}")
def get_generation_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Return one generation job with per-shot results and progress."""
    return generation_job_payload(_get_job(db, job_id))


@router.post("/api/generation-jobs/{job_id}/cancel")
def cancel_generation_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    """Cancel a queued or running generation job and return its final state."""
    job = _get_job(db, job_id)
    try:
        job = generation.cancel_generation_job(db, job)
    except generation.GenerationSelectionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task_queue.cancel_for(db, "generation", [job.id], "用户已取消生成")
    return generation_job_payload(job)


@router.get("/api/generation-jobs/{job_id}/shots/{shot_index}/video")
def download_generated_shot(
    job_id: str,
    shot_index: int,
    db: Session = Depends(get_db),
):
    """Stream a successfully generated shot video from the managed output directory."""
    job = _get_job(db, job_id)
    shot = next(
        (
            item
            for item in (job.result_json or {}).get("shots", [])
            if int(item.get("shot_index") or 0) == shot_index
        ),
        None,
    )
    if shot is None or shot.get("status") != "succeeded" or not shot.get("filename"):
        raise HTTPException(status_code=404, detail="生成结果不存在")
    path = generation.generation_media_path(
        job.prompt_project_id,
        job.id,
        str(shot["filename"]),
        get_settings(),
    )
    if path is None:
        raise HTTPException(status_code=404, detail="生成结果文件不存在")
    return FileResponse(
        path,
        media_type=shot.get("media_type") or "application/octet-stream",
        content_disposition_type="inline",
    )
