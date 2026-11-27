"""Timeline structural edits and targeted shot re-analysis."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..models import Job, Project, PromptProject, Shot, ShotEditEvent
from ..observability import current_request_id, request_id_ctx
from . import asr, capacity, fusion, media, vision
from .llm import LLMGateway
from .pipeline import project_dir
from .redaction import redact_exception
from .reference import rebuild_project_recipe

logger = logging.getLogger(__name__)

TIMELINE_MAPPING_WARNING = "参考视频时间轴已变化，请重新生成或校准镜头映射。"
SHOT_ANALYSIS_WARNING = "参考镜头已重新分析，提示词方案可能需要同步更新。"
SPLIT_PENDING_NOTE = "时间轴拆分后等待重新分析"
MERGE_PENDING_NOTE = "时间轴合并后等待重新分析"


class TimelineError(Exception):
    """Base error for timeline mutations."""


class TimelineNotFoundError(TimelineError):
    """The requested project or shot does not exist."""

    pass


class TimelineConflictError(TimelineError):
    """The project already has an active job or is otherwise busy."""

    pass


class TimelineValidationError(TimelineError):
    """The requested boundary, split, or merge is not structurally valid."""

    pass


class TimelineCapacityError(TimelineError):
    """Global worker capacity is exhausted."""

    pass


class TimelineCancelled(Exception):
    """Internal control-flow signal used when a user cancels the job."""

    pass


@dataclass(frozen=True)
class TimelineMutation:
    """Describe the queued job and affected records for one timeline mutation."""

    job_id: str
    action: str
    affected_shot_ids: list[int]
    prompt_projects_invalidated: int


def _ordered_shots(db: Session, project_id: str) -> list[Shot]:
    """Return all project shots in display order."""
    return list(
        db.scalars(
            select(Shot).where(Shot.project_id == project_id).order_by(Shot.index)
        ).all()
    )


def _ensure_idle(
    db: Session,
    project: Project,
    settings: Settings,
    *,
    capacity_reserved: bool = False,
) -> None:
    """Reject mutations while a project job is active or capacity is unavailable."""
    if project.status in {"queued", "running"}:
        raise TimelineConflictError("项目正在分析，暂时不能编辑时间轴")
    active = db.scalar(
        select(Job).where(
            Job.project_id == project.id,
            Job.status.in_(["queued", "running"]),
        )
    )
    if active is not None:
        raise TimelineConflictError("该项目已有活动任务，请等待完成后再编辑时间轴")
    if not capacity_reserved and not capacity.has_capacity(settings.max_active_jobs):
        raise TimelineCapacityError("当前分析任务已达并发上限，请稍后重试")


def _queue_job(
    db: Session,
    project: Project,
    action: str,
    shot_ids: list[int],
) -> Job:
    """Create a queued timeline job, mark the project queued, and flush the row."""
    job = Job(
        id=str(uuid.uuid4()),
        project_id=project.id,
        status="queued",
        step="timeline_queued",
        progress=0.0,
        metrics={"mode": "timeline", "action": action, "shot_ids": shot_ids},
    )
    project.status = "queued"
    db.add(job)
    db.flush()
    return job


def _audit(
    db: Session,
    project: Project,
    shot: Shot,
    source: str,
    changes: dict,
) -> None:
    """Record a per-shot audit event when there are actual field changes."""
    if not changes:
        return
    db.add(
        ShotEditEvent(
            project_id=project.id,
            shot_id=shot.id,
            shot_index=shot.index,
            source=source,
            changes=changes,
        )
    )


def invalidate_prompt_mappings(
    db: Session,
    project_id: str,
    warning: str = TIMELINE_MAPPING_WARNING,
) -> int:
    """Append a mapping warning to linked prompt plans and return the affected count.

    This helper mutates ORM objects but does not commit; the caller owns the
    surrounding timeline transaction.
    """
    projects = db.scalars(
        select(PromptProject).where(PromptProject.source_project_id == project_id)
    ).all()
    changed = 0
    for project in projects:
        plan = dict(project.plan_json or {})
        warnings = list(plan.get("warnings") or [])
        if warning in warnings:
            continue
        warnings.append(warning)
        plan["warnings"] = warnings
        project.plan_json = plan
        project.updated_at = datetime.now(timezone.utc)
        changed += 1
    return changed


def update_boundary(
    db: Session,
    project: Project,
    shot_id: int,
    boundary_s: float,
    settings: Settings,
    *,
    capacity_reserved: bool = False,
) -> TimelineMutation:
    """Move the boundary after one shot while preserving both minimum durations.

    The method writes a queued job and audit events, invalidates linked prompt
    mappings, and commits the transaction before returning.
    """
    _ensure_idle(db, project, settings, capacity_reserved=capacity_reserved)
    shots = _ordered_shots(db, project.id)
    position = next((index for index, shot in enumerate(shots) if shot.id == shot_id), None)
    if position is None:
        raise TimelineNotFoundError("镜头不存在")
    if position >= len(shots) - 1:
        raise TimelineValidationError("最后一个镜头没有可调整的右侧边界")

    left = shots[position]
    right = shots[position + 1]
    minimum = max(0.1, float(settings.min_shot_seconds))
    boundary = round(float(boundary_s), 3)
    lower = round(left.start_s + minimum, 3)
    upper = round(right.end_s - minimum, 3)
    if lower > upper:
        raise TimelineValidationError("这两个镜头过短，无法继续调整边界")
    if boundary < lower or boundary > upper:
        raise TimelineValidationError(
            f"边界必须位于 {lower:.3f}s 到 {upper:.3f}s 之间"
        )
    if abs(boundary - left.end_s) < 0.0005:
        raise TimelineValidationError("边界没有变化")

    left_before = round(left.end_s, 3)
    right_before = round(right.start_s, 3)
    left.end_s = boundary
    right.start_s = boundary
    _audit(
        db,
        project,
        left,
        "timeline_boundary",
        {"end_s": {"before": left_before, "after": boundary}},
    )
    _audit(
        db,
        project,
        right,
        "timeline_boundary",
        {"start_s": {"before": right_before, "after": boundary}},
    )
    invalidated = invalidate_prompt_mappings(db, project.id)
    affected = [left.id, right.id]
    job = _queue_job(db, project, "boundary", affected)
    db.commit()
    return TimelineMutation(job.id, "boundary", affected, invalidated)


def split_shot(
    db: Session,
    project: Project,
    shot_id: int,
    split_at: float,
    settings: Settings,
    *,
    capacity_reserved: bool = False,
) -> TimelineMutation:
    """Split a shot into two ordered shots and queue targeted re-analysis."""
    _ensure_idle(db, project, settings, capacity_reserved=capacity_reserved)
    shots = _ordered_shots(db, project.id)
    shot = next((item for item in shots if item.id == shot_id), None)
    if shot is None:
        raise TimelineNotFoundError("镜头不存在")

    minimum = max(0.1, float(settings.min_shot_seconds))
    point = round(float(split_at), 3)
    lower = round(shot.start_s + minimum, 3)
    upper = round(shot.end_s - minimum, 3)
    if lower > upper:
        raise TimelineValidationError("镜头过短，无法拆分")
    if point < lower or point > upper:
        raise TimelineValidationError(
            f"拆分点必须位于 {lower:.3f}s 到 {upper:.3f}s 之间"
        )

    original_end = round(shot.end_s, 3)
    analysis = dict(shot.analysis or {})
    analysis["evidence"] = [
        *(analysis.get("evidence") or []),
        SPLIT_PENDING_NOTE,
    ]
    for item in shots:
        if item.index > shot.index:
            item.index += 1
    new_shot = Shot(
        project_id=project.id,
        index=shot.index + 1,
        start_s=point,
        end_s=original_end,
        keyframe_path="",
        transcript="",
        origin=str(analysis.get("origin") or "unknown"),
        confidence=0.0,
        analysis=analysis,
    )
    shot.end_s = point
    db.add(new_shot)
    db.flush()
    _audit(
        db,
        project,
        shot,
        "timeline_split",
        {
            "end_s": {"before": original_end, "after": point},
            "split_at": {"before": original_end, "after": point},
        },
    )
    invalidated = invalidate_prompt_mappings(db, project.id)
    affected = [shot.id, new_shot.id]
    job = _queue_job(db, project, "split", affected)
    db.commit()
    return TimelineMutation(job.id, "split", affected, invalidated)


def merge_shots(
    db: Session,
    project: Project,
    shot_ids: list[int],
    settings: Settings,
    *,
    capacity_reserved: bool = False,
) -> TimelineMutation:
    """Merge two adjacent shots, reindex the remainder, and queue re-analysis."""
    _ensure_idle(db, project, settings, capacity_reserved=capacity_reserved)
    unique_ids = list(dict.fromkeys(int(item) for item in shot_ids))
    if len(unique_ids) != 2:
        raise TimelineValidationError("一次只能合并两个不同的相邻镜头")
    shots = _ordered_shots(db, project.id)
    positions = {shot.id: index for index, shot in enumerate(shots)}
    if any(shot_id not in positions for shot_id in unique_ids):
        raise TimelineNotFoundError("待合并镜头不存在")
    ordered = sorted(unique_ids, key=lambda item: positions[item])
    left = shots[positions[ordered[0]]]
    right = shots[positions[ordered[1]]]
    if right.index != left.index + 1:
        raise TimelineValidationError("只能合并相邻镜头")

    original_end = round(left.end_s, 3)
    merged_end = round(right.end_s, 3)
    left.end_s = merged_end
    left.transcript = " ".join(
        part for part in (left.transcript.strip(), right.transcript.strip()) if part
    )
    analysis = dict(left.analysis or {})
    analysis["evidence"] = [
        *(analysis.get("evidence") or []),
        MERGE_PENDING_NOTE,
    ]
    left.analysis = analysis
    _audit(
        db,
        project,
        left,
        "timeline_merge",
        {"end_s": {"before": original_end, "after": merged_end}},
    )
    db.delete(right)
    db.flush()
    remaining = [item for item in shots if item.id != right.id]
    for index, item in enumerate(remaining, start=1):
        item.index = index
    invalidated = invalidate_prompt_mappings(db, project.id)
    affected = [left.id]
    job = _queue_job(db, project, "merge", affected)
    db.commit()
    return TimelineMutation(job.id, "merge", affected, invalidated)


def queue_reanalysis(
    db: Session,
    project: Project,
    shot_id: int,
    settings: Settings,
    *,
    capacity_reserved: bool = False,
) -> TimelineMutation:
    """Queue keyframe and vision re-analysis for one existing shot."""
    _ensure_idle(db, project, settings, capacity_reserved=capacity_reserved)
    shot = db.scalar(
        select(Shot).where(Shot.id == shot_id, Shot.project_id == project.id)
    )
    if shot is None:
        raise TimelineNotFoundError("镜头不存在")
    invalidated = invalidate_prompt_mappings(db, project.id, SHOT_ANALYSIS_WARNING)
    affected = [shot.id]
    job = _queue_job(db, project, "reanalyze", affected)
    db.commit()
    return TimelineMutation(job.id, "reanalyze", affected, invalidated)


def _check_cancelled(db: Session, job: Job) -> None:
    """Refresh the job and abort execution when the user cancelled it."""
    db.refresh(job)
    if job.status == "cancelled":
        raise TimelineCancelled()


def _update_job(
    db: Session,
    job: Job,
    *,
    status: str | None = None,
    step: str | None = None,
    progress: float | None = None,
    error: str | None = None,
) -> None:
    """Persist job status and clamp progress into the public 0..1 range."""
    if status is not None:
        job.status = status
    if step is not None:
        job.step = step
    if progress is not None:
        job.progress = max(0.0, min(1.0, progress))
    if error is not None:
        job.error = error
    job.updated_at = datetime.now(timezone.utc)
    db.commit()


def _align_transcripts(
    db: Session,
    project: Project,
    shots: list[Shot],
    source: Path,
    ffmpeg: str,
    settings: Settings,
) -> str:
    """Best-effort transcribe the source and attach overlapping text to each shot."""
    if settings.asr_provider.lower().strip() in ("", "none"):
        return "disabled"
    root = project_dir(project.id, settings)
    audio_path = root / "audio.wav"
    try:
        media.extract_audio(ffmpeg, source, audio_path)
        transcripts = asr.transcribe(audio_path, settings)
    except Exception as exc:
        logger.warning("timeline ASR skipped: %s", exc)
        return "failed"
    for shot in shots:
        shot.transcript = fusion.attach_transcript(
            transcripts, shot.start_s, shot.end_s
        )
    db.commit()
    return "ok"


def _execute_timeline(
    db: Session,
    project: Project,
    job: Job,
    shot_ids: list[int],
    settings: Settings,
) -> None:
    """Re-probe, transcribe, extract frames, analyze selected shots, and rebuild the recipe.

    Progress and partial results are committed incrementally so the UI can
    observe the job. Cancellation is checked between expensive media steps.
    """
    source = Path(project.source_path)
    if not source.is_file():
        raise RuntimeError("源视频文件不存在")
    shots = list(
        db.scalars(
            select(Shot)
            .where(Shot.project_id == project.id, Shot.id.in_(shot_ids))
            .order_by(Shot.index)
        ).all()
    )
    if not shots:
        raise RuntimeError("没有找到需要重新分析的镜头")

    _update_job(db, job, status="running", step="timeline_probing", progress=0.03)
    meta = media.probe(source, settings)
    ffmpeg = media.resolve_ffmpeg(settings.ffmpeg_bin)
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请安装 imageio-ffmpeg 或系统 ffmpeg")
    _check_cancelled(db, job)

    _update_job(db, job, step="timeline_transcribing", progress=0.08)
    asr_status = _align_transcripts(db, project, shots, source, ffmpeg, settings)
    _check_cancelled(db, job)

    _update_job(db, job, step="timeline_extracting", progress=0.12)
    frames_dir = project_dir(project.id, settings) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[int, Path] = {}
    for index, shot in enumerate(shots, start=1):
        midpoint = shot.start_s + max(0.0, shot.end_s - shot.start_s) / 2
        frame = frames_dir / f"shot_{shot.id:06d}.jpg"
        media.extract_keyframe(ffmpeg, source, midpoint, frame)
        shot.keyframe_path = frame.relative_to(settings.data_dir).as_posix()
        frames[shot.id] = frame
        db.commit()
        _update_job(
            db, job, progress=0.12 + 0.33 * index / max(1, len(shots))
        )
        _check_cancelled(db, job)

    _update_job(db, job, step="timeline_analyzing", progress=0.48)
    gateway = LLMGateway(settings)
    for index, shot in enumerate(shots, start=1):
        analysis = vision.analyze_shot(
            gateway,
            frames[shot.id],
            shot.index,
            shot.start_s,
            shot.end_s,
            shot.transcript,
            meta,
        )
        shot.analysis = analysis.model_dump(mode="json")
        shot.origin = analysis.origin
        shot.confidence = analysis.confidence
        db.commit()
        _update_job(
            db, job, progress=0.48 + 0.4 * index / max(1, len(shots))
        )
        _check_cancelled(db, job)

    _update_job(db, job, step="timeline_fusing", progress=0.92)
    project = db.get(Project, project.id)
    if project is None:
        raise RuntimeError("项目已被删除")
    rebuild_project_recipe(project, settings)
    job.metrics = {
        **(job.metrics or {}),
        **gateway.stats(),
        **gateway.execution_metadata(asr_status=asr_status),
        "request_id": current_request_id(),
    }
    _update_job(db, job, status="done", step="done", progress=1.0, error="")
    project.status = "done"
    db.commit()


def run_timeline_reanalysis(
    project_id: str,
    job_id: str,
    shot_ids: list[int],
    *,
    reserved: bool = False,
) -> None:
    """Re-extract frames and analyze only the affected shots."""
    settings = get_settings()
    request_id_ctx.set(f"timeline-{job_id}")
    slot_held = reserved or capacity.is_reserved("analysis")
    if not slot_held:
        slot_held = capacity.acquire_job(settings.max_active_jobs, kind="analysis")
        if not slot_held:
            with SessionLocal() as db:
                project = db.get(Project, project_id)
                job = db.get(Job, job_id)
                if project is not None and job is not None:
                    job.status = "failed"
                    job.step = "failed"
                    job.error = "系统繁忙，当前分析任务已达并发上限，请稍后重试"
                    job.updated_at = datetime.now(timezone.utc)
                    project.status = "failed"
                    db.commit()
            return
    try:
        with SessionLocal() as db:
            project = db.get(Project, project_id)
            job = db.get(Job, job_id)
            if project is None or job is None:
                logger.error("timeline project or job missing: %s / %s", project_id, job_id)
                return
            try:
                _execute_timeline(db, project, job, shot_ids, settings)
            except TimelineCancelled:
                db.rollback()
                project = db.get(Project, project_id)
                job = db.get(Job, job_id)
                if project is not None and job is not None:
                    project.status = "cancelled"
                    job.status = "cancelled"
                    job.step = "cancelled"
                    job.error = "用户已取消任务"
                    job.updated_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception as exc:
                db.rollback()
                project = db.get(Project, project_id)
                job = db.get(Job, job_id)
                logger.exception("timeline reanalysis failed project=%s", project_id)
                if project is not None and job is not None:
                    project.status = "failed"
                    job.status = "failed"
                    job.step = "failed"
                    job.error = redact_exception(exc, settings, limit=500)
                    job.updated_at = datetime.now(timezone.utc)
                    db.commit()
    finally:
        if slot_held and not capacity.is_owned("analysis"):
            capacity.release_job("analysis")
