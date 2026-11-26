"""Process-wide concurrency accounting for analysis and generation workers."""

import threading


class CapacityExceeded(RuntimeError):
    """Raised when a caller requires a capacity slot that cannot be reserved."""

    pass


_lock = threading.Lock()
_active_jobs = 0


def active_jobs() -> int:
    """Return the current number of reserved worker slots."""
    with _lock:
        return _active_jobs


def has_capacity(limit: int) -> bool:
    """Check capacity without reserving a slot."""
    with _lock:
        return _active_jobs < max(1, limit)


def acquire_job(limit: int) -> bool:
    """Reserve one active-job slot without waiting, bounding queue depth."""
    global _active_jobs
    with _lock:
        if _active_jobs >= max(1, limit):
            return False
        _active_jobs += 1
        return True


def release_job() -> None:
    """Release one reserved worker slot, never going below zero."""
    global _active_jobs
    with _lock:
        _active_jobs = max(0, _active_jobs - 1)


def reset_for_tests() -> None:
    """Reset global capacity accounting for isolated tests."""
    global _active_jobs
    with _lock:
        _active_jobs = 0
