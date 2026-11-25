"""Durable video-generation job orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..models import GenerationJob, PromptProject
from ..observability import request_id_ctx
from ..schemas import GenerationJobCreate, PromptPlan, PromptShot
from . import capacity
from .generation_adapters import (
    SUPPORTED_ASPECT_RATIOS,
    GenerationProviderError,
    VideoGenerationRequest,
    create_adapter,
)
from .generation_adapters import capabilities as adapter_capabilities
from .redaction import redact_exception
from .retry import retry_call

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled"}


class GenerationPlanError(RuntimeError):
    pass


class GenerationSelectionError(ValueError):
    pass


def capabilities(settings: Settings) -> dict:
    return adapter_capabilities(settings)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_plan(project: PromptProject) -> PromptPlan:
    if project.status != "done" or not project.plan_json:
        raise GenerationPlanError("提示词方案尚未生成完成，暂不能生成视频")
    try:
        return PromptPlan.model_validate(project.plan_json)
    except Exception as exc:
        raise GenerationPlanError("提示词方案数据损坏，无法生成视频") from exc


def _selected_shots(plan: PromptPlan, requested: list[int]) -> list[PromptShot]:
    available = {shot.index: shot for shot in plan.shots}
    if not available:
        raise GenerationPlanError("提示词方案没有可生成的镜头")
    if not requested:
        return [available[index] for index in sorted(available)]
    indices = list(dict.fromkeys(int(index) for index in requested))
    missing = [index for index in indices if index not in available]
    if missing:
        raise GenerationSelectionError(
            "镜头不存在：" + ", ".join(str(index) for index in missing)
        )
    return [available[index] for index in indices]


def create_generation_job(
    db: Session,
    project: PromptProject,
    payload: GenerationJobCreate,
    settings: Settings,
) -> tuple[GenerationJob, bool]:
    adapter = create_adapter(settings)
    plan = _load_plan(project)
    selected = _selected_shots(plan, payload.shot_indices)
    aspect_ratio = payload.aspect_ratio or plan.aspect_ratio or "16:9"
    if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
        raise GenerationSelectionError(f"不支持的画面比例：{aspect_ratio}")

    idempotency_key = (payload.idempotency_key or "").strip() or None
    if idempotency_key:
        existing = db.scalar(
            select(GenerationJob).where(
                GenerationJob.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            if existing.prompt_project_id != project.id:
                raise GenerationSelectionError("幂等键已被其他项目使用")
            return existing, True

    job = GenerationJob(
        id=str(uuid.uuid4()),
        prompt_project_id=project.id,
        provider=adapter.name,
        model=payload.model or settings.video_model,
        status="queued",
        step="queued",
        progress=0.0,
        request_json={
            "shot_indices": [shot.index for shot in selected],
            "aspect_ratio": aspect_ratio,
            "model": payload.model or settings.video_model,
        },
        result_json={"provider": adapter.name, "shots": []},
        idempotency_key=idempotency_key,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(GenerationJob).where(
                GenerationJob.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise
        if existing.prompt_project_id != project.id:
            raise GenerationSelectionError("幂等键已被其他项目使用") from None
        return existing, True
    db.refresh(job)
    return job, False


def _job_directory(project_id: str, job_id: str, settings: Settings) -> Path:
    return (settings.data_dir / "generations" / project_id / job_id).resolve()


def _store_output(
    project_id: str,
    job_id: str,
    shot_index: int,
    extension: str,
    data: bytes,
    settings: Settings,
) -> str:
    suffix = extension.lower().lstrip(".")
    if suffix not in {"mp4", "webm", "mov", "svg"}:
        raise GenerationSelectionError("生成结果格式不受支持")
    directory = _job_directory(project_id, job_id, settings)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"shot-{shot_index:02d}.{suffix}"
    target = directory / filename
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    return filename


def generation_media_path(
    project_id: str,
    job_id: str,
    filename: str,
    settings: Settings,
) -> Path | None:
    root = _job_directory(project_id, job_id, settings)
    path = (root / filename).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def _mark_failed(
    db: Session,
    job: GenerationJob,
    message: str,
    *,
    step: str = "failed",
) -> None:
    job.status = "failed"
    job.step = step
    job.error = message[:1000]
    job.updated_at = _now()
    db.commit()


def run_generation_job(job_id: str, request_id: str | None = None) -> None:
    """Run one generation job sequentially and persist each shot."""
    settings = get_settings()
    trace_id = request_id or f"generation-{job_id}"
    token = request_id_ctx.set(trace_id)
    try:
        if not capacity.acquire_job(settings.max_active_generation_jobs):
            with SessionLocal() as db:
                job = db.get(GenerationJob, job_id)
                if job is not None and job.status not in TERMINAL_STATUSES:
                    _mark_failed(
                        db,
                        job,
                        "系统繁忙，当前同时视频生成任务已达上限，请稍后重试",
                    )
            return
        try:
            with SessionLocal() as db:
                job = db.get(GenerationJob, job_id)
                if job is None:
                    logger.error("generation job missing: %s", job_id)
                    return
                if job.status == "cancelled":
                    return
                project = db.get(PromptProject, job.prompt_project_id)
                if project is None:
                    _mark_failed(db, job, "提示词项目不存在")
                    return
                try:
                    plan = _load_plan(project)
                    adapter = create_adapter(settings)
                except GenerationPlanError as exc:
                    _mark_failed(db, job, str(exc))
                    return
                except GenerationProviderError as exc:
                    _mark_failed(db, job, str(exc))
                    return

                request_data = job.request_json or {}
                requested = [int(index) for index in request_data.get("shot_indices", [])]
                try:
                    selected = _selected_shots(plan, requested)
                except (GenerationPlanError, GenerationSelectionError) as exc:
                    _mark_failed(db, job, str(exc))
                    return

                aspect_ratio = str(request_data.get("aspect_ratio") or plan.aspect_ratio)
                model = str(request_data.get("model") or job.model or settings.video_model)
                job.status = "running"
                job.step = "submitting"
                job.progress = 0.02
                job.error = ""
                job.updated_at = _now()
                db.commit()

                results: list[dict] = []
                total = len(selected)
                for position, shot in enumerate(selected, start=1):
                    db.refresh(job)
                    if job.status == "cancelled":
                        return
                    job.step = f"shot-{shot.index}-{position}-of-{total}"
                    job.progress = min(0.96, 0.05 + 0.9 * (position - 1) / max(total, 1))
                    job.updated_at = _now()
                    db.commit()

                    duration = shot.duration or (shot.end_s - shot.start_s)
                    generation_request = VideoGenerationRequest(
                        shot_index=shot.index,
                        title=shot.subject or project.title,
                        prompt=shot.prompt,
                        negative_prompt=shot.negative_prompt,
                        duration_s=max(1.0, min(float(duration or 3.0), 10.0)),
                        aspect_ratio=aspect_ratio,
                        model=model,
                    )
                    try:
                        generated = retry_call(
                            lambda request=generation_request: adapter.generate(request),
                            attempts=settings.generation_retry_attempts,
                            base_delay=settings.retry_base_delay_s,
                            max_delay=settings.retry_max_delay_s,
                        )
                        filename = _store_output(
                            project.id,
                            job.id,
                            shot.index,
                            generated.extension,
                            generated.data,
                            settings,
                        )
                        results.append(
                            {
                                "shot_index": shot.index,
                                "status": "succeeded",
                                "filename": filename,
                                "media_type": generated.media_type,
                                "size_bytes": len(generated.data),
                                "duration_s": generation_request.duration_s,
                                "provider_job_id": generated.provider_job_id,
                                "warnings": generated.warnings,
                                "metadata": generated.metadata,
                                "error": "",
                            }
                        )
                    except Exception as exc:
                        logger.exception(
                            "generation shot failed project=%s job=%s shot=%s",
                            project.id,
                            job.id,
                            shot.index,
                        )
                        results.append(
                            {
                                "shot_index": shot.index,
                                "status": "failed",
                                "filename": "",
                                "media_type": "",
                                "size_bytes": 0,
                                "duration_s": generation_request.duration_s,
                                "provider_job_id": "",
                                "warnings": [],
                                "metadata": {},
                                "error": redact_exception(exc, settings, limit=400),
                            }
                        )
                    db.refresh(job)
                    if job.status == "cancelled":
                        return
                    job.result_json = {"provider": adapter.name, "shots": results}
                    job.progress = min(0.98, 0.05 + 0.9 * position / max(total, 1))
                    job.updated_at = _now()
                    db.commit()

                db.refresh(job)
                if job.status == "cancelled":
                    return
                succeeded = sum(item["status"] == "succeeded" for item in results)
                job.result_json = {"provider": adapter.name, "shots": results}
                job.progress = 1.0
                job.updated_at = _now()
                if succeeded == len(results) and results:
                    job.status = "succeeded"
                    job.step = "done"
                    job.error = ""
                elif succeeded:
                    job.status = "partial"
                    job.step = "partial"
                    job.error = f"部分镜头生成失败：成功 {succeeded} / {len(results)}"
                else:
                    job.status = "failed"
                    job.step = "failed"
                    job.error = "所有镜头生成失败，请检查 Prompt 或平台配置"
                db.commit()
        finally:
            capacity.release_job()
    except Exception as exc:
        logger.exception("generation job crashed: %s", job_id)
        with SessionLocal() as db:
            job = db.get(GenerationJob, job_id)
            if job is not None and job.status not in TERMINAL_STATUSES:
                _mark_failed(db, job, redact_exception(exc, settings, limit=800))
    finally:
        request_id_ctx.reset(token)


def cancel_generation_job(db: Session, job: GenerationJob) -> GenerationJob:
    if job.status not in {"queued", "running"}:
        raise GenerationSelectionError("该生成任务当前不可取消")
    job.status = "cancelled"
    job.step = "cancelled"
    job.error = "用户已取消生成"
    job.updated_at = _now()
    db.commit()
    db.refresh(job)
    return job
