import threading


class CapacityExceeded(RuntimeError):
    pass


_lock = threading.Lock()
_active_jobs = 0


def active_jobs() -> int:
    with _lock:
        return _active_jobs


def has_capacity(limit: int) -> bool:
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
    global _active_jobs
    with _lock:
        _active_jobs = max(0, _active_jobs - 1)


def reset_for_tests() -> None:
    global _active_jobs
    with _lock:
        _active_jobs = 0
