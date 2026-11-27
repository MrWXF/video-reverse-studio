"""Durable background-task queue with atomic claims, leases, and restart recovery."""

from __future__ import annotations

import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..db import SessionLocal
from ..models import (
    DeliveryReview,
    GenerationJob,
    Job,
    Project,
    PromptProject,
    TaskRun,
)
from . import capacity

logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:10]}"
_ACTIVE_STATUSES = {"queued", "running"}
_TERMINAL_STATUSES = {"done", "failed", "cancelled", "succeeded", "partial"}
_CAPACITY_KIND = {
    "analysis": "analysis",
    "timeline": "analysis",
    "prompt": "prompt",
    "review": "review",
    "generation": "generation",
}
_dispatcher_stop = threading.Event()
_dispatcher_thread: threading.Thread | None = None


def _now() -> datetime:
    """Return an aware UTC timestamp used by queue state transitions."""
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """Normalize SQLite's naive datetimes back to aware UTC values."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _factory(db: Session):
    """Build a session factory bound to the same engine as an open request session."""
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)


def enqueue(
    db: Session,
    kind: str,
    ref_id: str,
    *,
    payload: dict | None = None,
    request_id: str = "",
    max_attempts: int | None = None,
) -> TaskRun:
    """Persist a queued task or reuse the existing active task for the same reference."""
    existing = db.scalar(
        select(TaskRun).where(
            TaskRun.kind == kind,
            TaskRun.ref_id == ref_id,
            TaskRun.status.in_(list(_ACTIVE_STATUSES)),
        )
    )
    if existing is not None:
        return existing
    settings = get_settings()
    task = TaskRun(
        id=str(uuid.uuid4()),
        kind=kind,
        ref_id=ref_id,
        request_id=request_id[:80],
        payload_json=payload or {},
        status="queued",
        attempts=0,
        max_attempts=max_attempts or settings.task_max_attempts,
        available_at=_now(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def schedule(background, db: Session, task: TaskRun) -> None:
    """Claim a task in the request and run it immediately after the response."""
    settings = get_settings()
    now = _now()
    if task.status != "queued":
        raise RuntimeError("任务已被其他 worker 领取")
    task.status = "running"
    task.attempts += 1
    task.worker_id = WORKER_ID
    task.lease_until = now + timedelta(seconds=settings.task_lease_s)
    task.updated_at = now
    db.commit()
    attempts = task.attempts
    background.add_task(
        run_claimed,
        task.id,
        expected_attempts=attempts,
        reserved=True,
        reserved_kind=task.kind,
        session_factory=_factory(db),
    )


def cancel_for(db: Session, kind: str, ref_ids: list[str], reason: str) -> int:
    """Cancel queued/running queue rows for deleted or user-cancelled references."""
    if not ref_ids:
        return 0
    tasks = db.scalars(
        select(TaskRun).where(
            TaskRun.kind == kind,
            TaskRun.ref_id.in_(ref_ids),
            TaskRun.status.in_(list(_ACTIVE_STATUSES)),
        )
    ).all()
    for task in tasks:
        task.status = "cancelled"
        task.last_error = reason[:1000]
        task.lease_until = None
        task.updated_at = _now()
    if tasks:
        db.commit()
    return len(tasks)


def pending_counts(session_factory: Callable[[], Session] | None = None) -> dict:
    """Return queue depth grouped by active task kind for health checks."""
    factory = session_factory or SessionLocal
    counts: dict[str, int] = {}
    try:
        with factory() as db:
            tasks = db.scalars(
                select(TaskRun).where(TaskRun.status.in_(list(_ACTIVE_STATUSES)))
            ).all()
            for task in tasks:
                counts[task.kind] = counts.get(task.kind, 0) + 1
    except Exception:
        logger.exception("could not read task queue depth")
    return counts


def _claim_with_factory(
    task_id: str,
    session_factory: Callable[[], Session],
    *,
    lease_s: int,
) -> bool:
    """Atomically move one queued task to running and lease it to this worker."""
    now = _now()
    with session_factory() as db:
        task = db.get(TaskRun, task_id)
        if task is None or task.status != "queued":
            return False
        available = _aware(task.available_at)
        if available is not None and available > now:
            return False
        result = db.execute(
            update(TaskRun)
            .where(TaskRun.id == task_id, TaskRun.status == "queued")
            .values(
                status="running",
                attempts=TaskRun.attempts + 1,
                worker_id=WORKER_ID,
                lease_until=now + timedelta(seconds=lease_s),
                updated_at=now,
            )
        )
        db.commit()
        return result.rowcount == 1


def claim_next(
    session_factory: Callable[[], Session],
    *,
    lease_s: int,
) -> str | None:
    """Claim the oldest ready task, returning its id or ``None`` when the queue is idle."""
    with session_factory() as db:
        candidates = db.scalars(
            select(TaskRun)
            .where(TaskRun.status == "queued")
            .order_by(TaskRun.available_at, TaskRun.created_at)
            .limit(20)
        ).all()
        now = _now()
        ids = [
            task.id
            for task in candidates
            if task.available_at is None or _aware(task.available_at) <= now
        ]
    for task_id in ids:
        if _claim_with_factory(task_id, session_factory, lease_s=lease_s):
            return task_id
    return None


def complete(
    task_id: str,
    session_factory: Callable[[], Session],
    *,
    expected_attempts: int | None = None,
) -> None:
    """Mark a successfully executed task as done when this worker still owns it."""
    with session_factory() as db:
        statement = update(TaskRun).where(
            TaskRun.id == task_id,
            TaskRun.status == "running",
            TaskRun.worker_id == WORKER_ID,
        )
        if expected_attempts is not None:
            statement = statement.where(TaskRun.attempts == expected_attempts)
        db.execute(
            statement.values(
                status="done",
                lease_until=None,
                worker_id="",
                updated_at=_now(),
            )
        )
        db.commit()


def fail(
    task_id: str,
    message: str,
    session_factory: Callable[[], Session],
    *,
    retryable: bool = True,
    delay_s: float | None = None,
    expected_attempts: int | None = None,
) -> None:
    """Retry a failed task within its attempt budget when this worker still owns it."""
    settings = get_settings()
    with session_factory() as db:
        task = db.get(TaskRun, task_id)
        if (
            task is None
            or task.status != "running"
            or task.worker_id != WORKER_ID
            or (
                expected_attempts is not None
                and task.attempts != expected_attempts
            )
        ):
            return
        owned = (
            TaskRun.id == task_id,
            TaskRun.status == "running",
            TaskRun.worker_id == WORKER_ID,
            TaskRun.attempts == task.attempts,
        )
        now = _now()
        retrying = retryable and task.attempts < task.max_attempts
        values = {
            "last_error": message[:1000],
            "lease_until": None,
            "worker_id": "",
            "updated_at": now,
        }
        if retrying:
            values.update(
                status="queued",
                available_at=now
                + timedelta(
                    seconds=settings.retry_base_delay_s
                    if delay_s is None
                    else delay_s
                ),
            )
        else:
            values["status"] = "failed"
        result = db.execute(update(TaskRun).where(*owned).values(**values))
        db.commit()
        if result.rowcount == 1 and not retrying:
            mark_entity_failed(db, task, message)


def mark_entity_failed(
    db: Session,
    task: TaskRun,
    message: str,
    *,
    status: str = "failed",
) -> None:
    """Mirror a terminal queue failure onto the user-visible job record."""
    now = _now()
    if task.kind == "prompt":
        project = db.get(PromptProject, task.ref_id)
        if project is not None and project.status not in _TERMINAL_STATUSES:
            project.status = status
            project.step = status
            project.error = message[:1000]
            project.updated_at = now
        db.commit()
        return
    if task.kind == "review":
        review = db.get(DeliveryReview, task.ref_id)
        if review is not None and review.status not in _TERMINAL_STATUSES:
            review.status = status
            review.step = status
            review.error = message[:1000]
            review.updated_at = now
        db.commit()
        return
    if task.kind == "generation":
        generation = db.get(GenerationJob, task.ref_id)
        if generation is not None and generation.status not in _TERMINAL_STATUSES:
            generation.status = status
            generation.step = status
            generation.error = message[:1000]
            generation.updated_at = now
        db.commit()
        return

    job = db.get(Job, task.ref_id)
    if job is not None and job.status not in _TERMINAL_STATUSES:
        job.status = status
        job.step = status
        job.error = message[:1000]
        job.updated_at = now
        project_id = (task.payload_json or {}).get("project_id")
        project = db.get(Project, project_id) if project_id else job.project
        if project is not None and project.status not in _TERMINAL_STATUSES:
            project.status = status
    db.commit()


def _handler(task: TaskRun):
    """Resolve and invoke the service function for one queued task."""
    payload = task.payload_json or {}
    if task.kind == "analysis":
        from . import pipeline

        return pipeline.run_pipeline(
            str(payload["project_id"]),
            task.ref_id,
            request_id=task.request_id or None,
        )
    if task.kind == "timeline":
        from . import timeline

        return timeline.run_timeline_reanalysis(
            str(payload["project_id"]),
            task.ref_id,
            [int(value) for value in payload.get("shot_ids", [])],
        )
    if task.kind == "prompt":
        from . import prompt_generation

        return prompt_generation.run_prompt_generation(
            task.ref_id,
            request_id=task.request_id or None,
        )
    if task.kind == "review":
        from . import delivery_review

        return delivery_review.run_delivery_review(
            task.ref_id,
            request_id=task.request_id or None,
        )
    if task.kind == "generation":
        from . import generation

        return generation.run_generation_job(
            task.ref_id,
            request_id=task.request_id or None,
        )
    raise ValueError(f"未知任务类型：{task.kind}")


def _invoke_handler(task: TaskRun, *, reserved: bool):
    """Invoke a task handler while marking a request-reserved capacity slot."""
    if not reserved:
        return _handler(task)
    kind = _CAPACITY_KIND.get(task.kind, task.kind)
    with capacity.claimed(kind):
        return _handler(task)


@contextmanager
def _lease_heartbeat(
    task_id: str,
    *,
    expected_attempts: int,
    session_factory: Callable[[], Session],
    lease_s: int,
):
    """Extend the lease of a long-running task without risking a stolen claim."""
    stop = threading.Event()
    interval = max(5.0, lease_s / 3)

    def beat() -> None:
        while not stop.wait(interval):
            now = _now()
            with session_factory() as db:
                result = db.execute(
                    update(TaskRun)
                    .where(
                        TaskRun.id == task_id,
                        TaskRun.status == "running",
                        TaskRun.worker_id == WORKER_ID,
                        TaskRun.attempts == expected_attempts,
                    )
                    .values(
                        lease_until=now + timedelta(seconds=lease_s),
                        updated_at=now,
                    )
                )
                db.commit()
                if result.rowcount != 1:
                    return

    thread = threading.Thread(
        target=beat,
        name=f"task-lease-{task_id[:8]}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2.0)


def _execute_claimed(
    task_id: str,
    session_factory: Callable[[], Session],
    *,
    reserved: bool,
    reserved_kind: str | None = None,
    expected_attempts: int | None = None,
) -> None:
    """Execute one already-claimed task and persist its terminal queue state."""
    task_snapshot: TaskRun | None = None
    try:
        with session_factory() as db:
            task = db.get(TaskRun, task_id)
            if (
                task is None
                or task.status != "running"
                or task.worker_id != WORKER_ID
                or (
                    expected_attempts is not None
                    and task.attempts != expected_attempts
                )
            ):
                return
            task_snapshot = TaskRun(
                id=task.id,
                kind=task.kind,
                ref_id=task.ref_id,
                request_id=task.request_id,
                payload_json=dict(task.payload_json or {}),
                status=task.status,
                attempts=task.attempts,
                max_attempts=task.max_attempts,
            )
        with _lease_heartbeat(
            task_id,
            expected_attempts=task_snapshot.attempts,
            session_factory=session_factory,
            lease_s=get_settings().task_lease_s,
        ):
            _invoke_handler(task_snapshot, reserved=reserved)
    except Exception as exc:
        if task_snapshot is not None:
            logger.exception(
                "task failed kind=%s ref=%s",
                task_snapshot.kind,
                task_snapshot.ref_id,
            )
        fail(
            task_id,
            f"{type(exc).__name__}: {exc}",
            session_factory,
            retryable=True,
            expected_attempts=task_snapshot.attempts if task_snapshot else None,
        )
        return
    else:
        complete(
            task_id,
            session_factory,
            expected_attempts=task_snapshot.attempts if task_snapshot else None,
        )
    finally:
        if reserved:
            kind = reserved_kind
            if task_snapshot is not None:
                kind = _CAPACITY_KIND.get(task_snapshot.kind, task_snapshot.kind)
            capacity.release_job(
                _CAPACITY_KIND.get(kind, kind) if kind else "analysis"
            )


def run_task(
    task_id: str,
    *,
    reserved: bool = False,
    session_factory: Callable[[], Session] | None = None,
) -> bool:
    """Claim and run one task; return ``False`` when another worker already claimed it."""
    factory = session_factory or SessionLocal
    settings = get_settings()
    if not _claim_with_factory(task_id, factory, lease_s=settings.task_lease_s):
        return False
    _execute_claimed(task_id, factory, reserved=reserved)
    return True


def run_claimed(
    task_id: str,
    *,
    expected_attempts: int,
    reserved: bool = False,
    reserved_kind: str | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> bool:
    """Execute a task already claimed by the request that created it."""
    factory = session_factory or SessionLocal
    with factory() as db:
        task = db.get(TaskRun, task_id)
        if (
            task is None
            or task.status != "running"
            or task.worker_id != WORKER_ID
            or task.attempts != expected_attempts
        ):
            if reserved:
                capacity.release_job(
                    _CAPACITY_KIND.get(
                        reserved_kind or (task.kind if task is not None else "analysis"),
                        reserved_kind or (task.kind if task is not None else "analysis"),
                    )
                )
            return False
    _execute_claimed(
        task_id,
        factory,
        reserved=reserved,
        reserved_kind=reserved_kind,
        expected_attempts=expected_attempts,
    )
    return True


def recover_expired(session_factory: Callable[[], Session] | None = None) -> int:
    """Return expired leases to the queue or fail them after exhausting attempts."""
    factory = session_factory or SessionLocal
    now = _now()
    recovered = 0
    with factory() as db:
        tasks = db.scalars(select(TaskRun).where(TaskRun.status == "running")).all()
        for task in tasks:
            lease_until = _aware(task.lease_until)
            if lease_until is not None and lease_until > now:
                continue
            task.lease_until = None
            task.worker_id = ""
            task.updated_at = now
            if task.attempts < task.max_attempts:
                task.status = "queued"
                task.available_at = now
            else:
                task.status = "failed"
                task.last_error = "任务租约过期且重试次数已用尽"
            recovered += 1
        db.commit()
        failed_ids = [
            task.id
            for task in db.scalars(
                select(TaskRun).where(TaskRun.status == "failed")
            ).all()
            if task.last_error == "任务租约过期且重试次数已用尽"
        ]
        for task_id in failed_ids:
            task = db.get(TaskRun, task_id)
            if task is not None:
                mark_entity_failed(db, task, task.last_error)
    return recovered


def fail_orphaned_entities(session_factory: Callable[[], Session] | None = None) -> int:
    """Fail legacy queued/running rows that have no durable queue entry."""
    factory = session_factory or SessionLocal
    message = "任务没有可恢复的队列记录，请重新提交"
    changed = 0
    with factory() as db:
        active = db.scalars(
            select(TaskRun).where(TaskRun.status.in_(list(_ACTIVE_STATUSES)))
        ).all()
        active_refs = {(task.kind, task.ref_id) for task in active}
        now = _now()
        jobs = db.scalars(select(Job).where(Job.status.in_(["queued", "running"]))).all()
        for job in jobs:
            kinds = {"analysis", "timeline"}
            if any((kind, job.id) in active_refs for kind in kinds):
                continue
            job.status = "failed"
            job.step = "failed"
            job.error = message
            job.updated_at = now
            project = db.get(Project, job.project_id)
            if project is not None and project.status in {"queued", "running"}:
                project.status = "failed"
            changed += 1
        prompts = db.scalars(
            select(PromptProject).where(PromptProject.status.in_(["queued", "running"]))
        ).all()
        for project in prompts:
            if ("prompt", project.id) in active_refs:
                continue
            project.status = "failed"
            project.step = "failed"
            project.error = message
            project.updated_at = now
            changed += 1
        reviews = db.scalars(
            select(DeliveryReview).where(DeliveryReview.status.in_(["queued", "running"]))
        ).all()
        for review in reviews:
            if ("review", review.id) in active_refs:
                continue
            review.status = "failed"
            review.step = "failed"
            review.error = message
            review.updated_at = now
            changed += 1
        generations = db.scalars(
            select(GenerationJob).where(GenerationJob.status.in_(["queued", "running"]))
        ).all()
        for job in generations:
            if ("generation", job.id) in active_refs:
                continue
            job.status = "failed"
            job.step = "failed"
            job.error = message
            job.updated_at = now
            changed += 1
        if changed:
            db.commit()
    return changed


def _dispatch_loop() -> None:
    """Continuously claim queued tasks until application shutdown."""
    settings = get_settings()
    while not _dispatcher_stop.wait(settings.task_poll_interval_s):
        try:
            recover_expired(SessionLocal)
            for _ in range(8):
                task_id = claim_next(SessionLocal, lease_s=settings.task_lease_s)
                if task_id is None:
                    break
                _execute_claimed(task_id, SessionLocal, reserved=False)
        except Exception:
            logger.exception("task dispatcher iteration failed")


def start_dispatcher() -> None:
    """Recover expired work and start the process-local dispatcher thread once."""
    global _dispatcher_thread
    recover_expired()
    fail_orphaned_entities()
    if _dispatcher_thread is not None and _dispatcher_thread.is_alive():
        return
    _dispatcher_stop.clear()
    _dispatcher_thread = threading.Thread(
        target=_dispatch_loop,
        name="task-dispatcher",
        daemon=True,
    )
    _dispatcher_thread.start()


def stop_dispatcher() -> None:
    """Signal the dispatcher thread to stop during application shutdown."""
    _dispatcher_stop.set()
    if _dispatcher_thread is not None and _dispatcher_thread.is_alive():
        _dispatcher_thread.join(timeout=2.0)
