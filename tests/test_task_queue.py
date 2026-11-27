from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Job, Project, TaskRun
from app.services import capacity, task_queue


class _Background:
    def __init__(self):
        self.calls = []

    def add_task(self, function, *args, **kwargs):
        self.calls.append((function, args, kwargs))


def _queue_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Project(id="p1", title="queue", source_path="/tmp/p1.mp4", status="queued"))
        db.add(Job(id="j1", project_id="p1", status="queued", step="queued"))
        db.commit()
        task_queue.enqueue(
            db,
            "analysis",
            "j1",
            payload={"project_id": "p1"},
            request_id="trace-1",
        )
    return factory


def test_task_claim_is_exclusive_and_recovers_expired_lease():
    factory = _queue_env()

    task_id = task_queue.claim_next(factory, lease_s=60)
    assert task_id is not None
    assert task_queue.claim_next(factory, lease_s=60) is None

    with factory() as db:
        task = db.get(TaskRun, task_id)
        assert task.status == "running"
        assert task.attempts == 1
        task.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    assert task_queue.recover_expired(factory) == 1
    with factory() as db:
        task = db.get(TaskRun, task_id)
        assert task.status == "queued"

    reclaimed = task_queue.claim_next(factory, lease_s=60)
    assert reclaimed == task_id
    task_queue.complete(task_id, factory)
    with factory() as db:
        assert db.get(TaskRun, task_id).status == "done"


def test_enqueue_reuses_active_task_for_same_reference():
    factory = _queue_env()
    with factory() as db:
        first = db.scalar(select(TaskRun))
        second = task_queue.enqueue(
            db,
            "analysis",
            "j1",
            payload={"project_id": "p1"},
            request_id="trace-2",
        )
        assert second.id == first.id
        assert db.scalar(select(TaskRun).where(TaskRun.ref_id == "j1")).id == first.id


def test_cancelled_scheduled_task_releases_reserved_capacity(monkeypatch):
    capacity.reset_for_tests()
    factory = _queue_env()
    background = _Background()
    with factory() as db:
        task = db.scalar(select(TaskRun))
        assert capacity.reserve("analysis", 1)
        task_queue.schedule(background, db, task)
        task_queue.cancel_for(db, "analysis", ["j1"], "用户已取消")

    function, args, kwargs = background.calls[0]
    assert function(*args, **kwargs) is False
    assert capacity.active_jobs() == 0


def test_scheduled_success_and_failure_release_reserved_capacity(monkeypatch):
    capacity.reset_for_tests()
    factory = _queue_env()
    monkeypatch.setattr(task_queue, "_handler", lambda _task: None)
    background = _Background()
    with factory() as db:
        task = db.scalar(select(TaskRun))
        assert capacity.reserve("analysis", 1)
        task_queue.schedule(background, db, task)
    function, args, kwargs = background.calls[0]
    assert function(*args, **kwargs) is True
    assert capacity.active_jobs() == 0

    capacity.reset_for_tests()
    factory = _queue_env()
    background = _Background()

    def fail(_task):
        raise RuntimeError("boom")

    monkeypatch.setattr(task_queue, "_handler", fail)
    with factory() as db:
        task = db.scalar(select(TaskRun))
        task.max_attempts = 1
        db.commit()
        assert capacity.reserve("analysis", 1)
        task_queue.schedule(background, db, task)
    function, args, kwargs = background.calls[0]
    assert function(*args, **kwargs) is True
    assert capacity.active_jobs() == 0
    with factory() as db:
        assert db.scalar(select(TaskRun)).status == "failed"


def test_cancelled_stale_claim_is_not_executed_and_releases_capacity(monkeypatch):
    capacity.reset_for_tests()
    factory = _queue_env()
    called: list[str] = []
    monkeypatch.setattr(task_queue, "_handler", lambda task: called.append(task.id))

    task_id = task_queue.claim_next(factory, lease_s=60)
    assert task_id is not None
    with factory() as db:
        task = db.get(TaskRun, task_id)
        task.status = "cancelled"
        task.worker_id = ""
        db.commit()

    assert capacity.reserve("analysis", 1)
    task_queue._execute_claimed(
        task_id,
        factory,
        reserved=True,
        reserved_kind="analysis",
    )

    assert called == []
    assert capacity.active_jobs() == 0


def test_old_attempt_cannot_finish_a_reclaimed_task():
    factory = _queue_env()
    task_id = task_queue.claim_next(factory, lease_s=60)
    assert task_id is not None
    with factory() as db:
        task = db.get(TaskRun, task_id)
        task.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    assert task_queue.recover_expired(factory) == 1
    assert task_queue.claim_next(factory, lease_s=60) == task_id

    task_queue.complete(task_id, factory, expected_attempts=1)
    task_queue.fail(
        task_id,
        "stale failure",
        factory,
        retryable=False,
        expected_attempts=1,
    )
    with factory() as db:
        task = db.get(TaskRun, task_id)
        assert task.status == "running"
        assert task.attempts == 2
        assert db.get(Job, "j1").status == "queued"

    task_queue.complete(task_id, factory, expected_attempts=2)
    with factory() as db:
        assert db.get(TaskRun, task_id).status == "done"
