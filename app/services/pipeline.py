"""Video analysis pipeline with bounded retries and concurrency."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import SessionLocal
from ..models import Job, Project, Shot
from ..observability import current_request_id, request_id_ctx
from ..schemas import ShotAnalysis
from . import asr, capacity, fusion, media, vision
from . import recipe as recipe_service
from .llm import LLMGateway
from .redaction import redact_exception
from .retry import is_retryable_exception, retry_delay

logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


def project_dir(project_id: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.data_dir / "projects" / project_id


def _update_job(
    db: Session,
    job: Job,
    *,
    status: str | None = None,
    step: str | None = None,
    progress: float | None = None,
    error: str | None = None,
) -> None:
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


def run_pipeline(
    project_id: str,
    job_id: str,
    request_id: str | None = None,
) -> None:
    """Run the reverse-analysis job with admission control and retries."""
    settings = get_settings()
    trace_id = request_id or f"job-{job_id}"
    token = request_id_ctx.set(trace_id)
    try:
        with SessionLocal() as db:
            project = db.get(Project, project_id)
            job = db.get(Job, job_id)
            if project is None or job is None:
                logger.error("project or job missing: %s / %s", project_id, job_id)
                return
            if not capacity.acquire_job(settings.max_active_jobs):
                project.status = "failed"
                job.status = "failed"
                job.step = "failed"
                job.error = "系统繁忙，当前并发分析任务已达上限，请稍后重试"
                job.updated_at = datetime.now(timezone.utc)
                db.commit()
                return
            try:
                attempt = 1
                while True:
                    try:
                        _execute(db, project, job, settings)
                        break
                    except JobCancelled:
                        db.rollback()
                        project.status = "cancelled"
                        job.status = "cancelled"
                        job.step = "cancelled"
                        job.error = "用户已取消任务"
                        job.updated_at = datetime.now(timezone.utc)
                        db.commit()
                        break
                    except Exception as exc:
                        db.rollback()
                        project = db.get(Project, project_id)
                        job = db.get(Job, job_id)
                        if project is None or job is None:
                            logger.error("project or job disappeared during retry")
                            break
                        if job.status == "cancelled" or project.status == "cancelled":
                            job.status = "cancelled"
                            job.step = "cancelled"
                            job.error = "用户已取消任务"
                            job.updated_at = datetime.now(timezone.utc)
                            db.commit()
                            break
                        retryable = is_retryable_exception(exc)
                        if retryable and attempt < settings.retry_max_attempts:
                            delay = retry_delay(
                                attempt,
                                settings.retry_base_delay_s,
                                settings.retry_max_delay_s,
                            )
                            logger.warning(
                                "pipeline transient failure project=%s attempt=%s delay=%.2fs",
                                project_id,
                                attempt,
                                delay,
                            )
                            job.status = "running"
                            job.step = "retrying"
                            job.error = redact_exception(exc, settings, limit=500)
                            job.updated_at = datetime.now(timezone.utc)
                            db.commit()
                            time.sleep(delay)
                            attempt += 1
                            continue

                        logger.exception("pipeline failed for project %s", project_id)
                        project.status = "failed"
                        job.status = "failed"
                        job.step = "failed"
                        job.error = redact_exception(exc, settings)
                        job.updated_at = datetime.now(timezone.utc)
                        db.commit()
                        break
            finally:
                capacity.release_job()
    finally:
        request_id_ctx.reset(token)


def _execute(db: Session, project: Project, job: Job, settings: Settings) -> None:
    """Perform one full analysis attempt. The operation is idempotent."""
    root = project_dir(project.id, settings)
    source = Path(project.source_path)
    if not source.exists():
        raise FileNotFoundError(f"源视频不存在：{source}")

    _check_cancelled(db, job)
    _update_job(db, job, status="running", step="probing", progress=0.03)
    project.status = "running"
    db.commit()

    meta = media.probe(source, settings)
    project.duration = meta.duration
    project.width = meta.width
    project.height = meta.height
    project.fps = meta.fps
    db.commit()
    _check_cancelled(db, job)

    _update_job(db, job, step="segmenting", progress=0.1)
    segments = media.detect_shots(source, meta, settings)
    if not segments:
        raise RuntimeError("未能生成任何分镜")
    _check_cancelled(db, job)

    ffmpeg = media.resolve_ffmpeg(settings.ffmpeg_bin)
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请安装 imageio-ffmpeg 或系统 ffmpeg")

    _update_job(db, job, step="extracting", progress=0.15)
    frames_dir = root / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    keyframes: list[Path] = []
    for index, (start, end) in enumerate(segments):
        midpoint = start + max(0.0, end - start) / 2
        frame = frames_dir / f"shot_{index + 1:04d}.jpg"
        media.extract_keyframe(ffmpeg, source, midpoint, frame)
        keyframes.append(frame)
        _update_job(db, job, progress=0.15 + 0.3 * (index + 1) / len(segments))
    _check_cancelled(db, job)

    _update_job(db, job, step="transcribing", progress=0.47)
    transcripts = _transcribe(root, source, ffmpeg, settings)
    _check_cancelled(db, job)

    _update_job(db, job, step="analyzing", progress=0.5)
    gateway = LLMGateway(settings)
    analyses = _analyze_shots(
        gateway, keyframes, segments, transcripts, meta, settings, db, job
    )
    _check_cancelled(db, job)

    _update_job(db, job, step="fusing", progress=0.9)
    shot_rows: list[dict] = []
    db.query(Shot).filter(Shot.project_id == project.id).delete()
    for index, (start, end) in enumerate(segments):
        analysis: ShotAnalysis = analyses[index]
        transcript = fusion.attach_transcript(transcripts, start, end)
        keyframe_rel = keyframes[index].relative_to(settings.data_dir).as_posix()
        db.add(
            Shot(
                project_id=project.id,
                index=index + 1,
                start_s=start,
                end_s=end,
                keyframe_path=keyframe_rel,
                transcript=transcript,
                origin=analysis.origin,
                confidence=analysis.confidence,
                analysis=analysis.model_dump(),
            )
        )
        shot_rows.append(
            {
                "index": index + 1,
                "start_s": start,
                "end_s": end,
                "analysis": analysis,
                "transcript": transcript,
            }
        )
    db.commit()
    _check_cancelled(db, job)

    recipe = fusion.build_recipe(
        title=project.title,
        source_filename=source.name,
        meta=meta,
        shot_rows=shot_rows,
    )
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "video.md").write_text(
        recipe_service.render_markdown(recipe), encoding="utf-8"
    )
    (output_dir / "video.json").write_text(
        recipe_service.render_json(recipe), encoding="utf-8"
    )

    job.metrics = {
        **gateway.stats(),
        "request_id": current_request_id(),
    }
    _update_job(db, job, status="done", step="done", progress=1.0, error="")
    project.status = "done"
    db.commit()


def _check_cancelled(db: Session, job: Job) -> None:
    """Raise when the user cancelled the job from another request."""
    db.refresh(job)
    if job.status == "cancelled":
        raise JobCancelled()


def _transcribe(
    root: Path, source: Path, ffmpeg: str, settings: Settings
) -> list[dict]:
    """Optionally transcribe audio; ASR failure must not fail the whole job."""
    if settings.asr_provider.lower().strip() in ("", "none"):
        return []
    audio_path = root / "audio.wav"
    try:
        media.extract_audio(ffmpeg, source, audio_path)
        return asr.transcribe(audio_path, settings)
    except Exception as exc:
        logger.warning("ASR skipped: %s", exc)
        return []


def _analyze_shots(
    gateway: LLMGateway,
    keyframes: list[Path],
    segments: list[tuple[float, float]],
    transcripts: list[dict],
    meta: media.VideoMeta,
    settings: Settings,
    db: Session,
    job: Job,
) -> list[ShotAnalysis]:
    """Analyze keyframes concurrently while preserving timeline order."""
    results: list[ShotAnalysis] = []

    def work(index: int) -> ShotAnalysis:
        start, end = segments[index]
        transcript = fusion.attach_transcript(transcripts, start, end)
        return vision.analyze_shot(
            gateway, keyframes[index], index + 1, start, end, transcript, meta
        )

    workers = max(1, min(settings.llm_concurrency, 8))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for done, result in enumerate(executor.map(work, range(len(segments))), start=1):
            results.append(result)
            _update_job(db, job, progress=0.5 + 0.38 * done / len(segments))
            _check_cancelled(db, job)
    return results
