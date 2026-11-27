"""Process-wide, per-workload concurrency accounting for background workers."""

import threading
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar


class CapacityExceeded(RuntimeError):
    """Raised when a caller requires a capacity slot that cannot be reserved."""

    pass


_lock = threading.Lock()
_active_jobs: dict[str, int] = defaultdict(int)
_reserved_kinds: ContextVar[frozenset[str]] = ContextVar(
    "capacity_reserved_kinds", default=frozenset()
)
_owned_kinds: ContextVar[frozenset[str]] = ContextVar(
    "capacity_owned_kinds", default=frozenset()
)


def is_reserved(kind: str) -> bool:
    """Return whether the current execution context already owns a slot."""
    return kind in _reserved_kinds.get()


def is_owned(kind: str) -> bool:
    """Return whether the queue owns the release for the current slot."""
    return kind in _owned_kinds.get()


@contextmanager
def claimed(kind: str):
    """Mark a workload slot as pre-reserved for the duration of a task."""
    current = _reserved_kinds.get()
    token = _reserved_kinds.set(current | {kind})
    owned = _owned_kinds.get()
    owned_token = _owned_kinds.set(owned | {kind})
    try:
        yield
    finally:
        _owned_kinds.reset(owned_token)
        _reserved_kinds.reset(token)


def active_jobs(kind: str | None = None) -> int:
    """Return reserved slots for one workload, or the total across all workloads."""
    with _lock:
        if kind is not None:
            return _active_jobs.get(kind, 0)
        return sum(_active_jobs.values())


def active_by_kind() -> dict[str, int]:
    """Return a snapshot of active reservations grouped by workload."""
    with _lock:
        return {key: value for key, value in _active_jobs.items() if value}


def has_capacity(limit: int, kind: str = "analysis") -> bool:
    """Check capacity without reserving a slot."""
    with _lock:
        return _active_jobs.get(kind, 0) < max(1, limit)


def reserve(kind: str, limit: int) -> bool:
    """Atomically reserve one slot for a workload without waiting."""
    with _lock:
        if _active_jobs.get(kind, 0) >= max(1, limit):
            return False
        _active_jobs[kind] += 1
        return True


def acquire_job(limit: int, kind: str = "analysis") -> bool:
    """Reserve one active-job slot without waiting, bounding queue depth."""
    return reserve(kind, limit)


def release_job(kind: str = "analysis") -> None:
    """Release one reserved workload slot, never going below zero."""
    with _lock:
        current = _active_jobs.get(kind, 0)
        if current <= 1:
            _active_jobs.pop(kind, None)
        else:
            _active_jobs[kind] = current - 1


def reset_for_tests() -> None:
    """Reset global capacity accounting for isolated tests."""
    with _lock:
        _active_jobs.clear()
    _reserved_kinds.set(frozenset())
    _owned_kinds.set(frozenset())
