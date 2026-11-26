"""Shared retry classification and bounded exponential-backoff helpers."""

import logging
import subprocess
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableServiceError(RuntimeError):
    """An expected transient service failure that is safe to retry."""


def is_retryable_exception(exc: BaseException) -> bool:
    """Classify transient provider, timeout, and process errors as retryable."""
    if isinstance(
        exc,
        (RetryableServiceError, TimeoutError, ConnectionError, subprocess.TimeoutExpired),
    ):
        return True
    name = type(exc).__name__.lower()
    return any(
        marker in name
        for marker in (
            "apiconnectionerror",
            "apitimeouterror",
            "internalservererror",
            "ratelimiterror",
            "serviceunavailable",
            "readtimeout",
        )
    )


def retry_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Return an exponential backoff delay for a 1-based attempt."""
    return min(max_delay, base_delay * (2 ** max(0, attempt - 1)))


def retry_call(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.8,
    max_delay: float = 8.0,
    retry_if: Callable[[BaseException], bool] = is_retryable_exception,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run an operation with bounded exponential-backoff retries."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt >= attempts or not retry_if(exc):
                raise
            delay = retry_delay(attempt, base_delay, max_delay)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            else:
                logger.warning(
                    "retrying transient failure attempt=%s delay=%.2fs error=%s",
                    attempt,
                    delay,
                    exc,
                )
            sleep(delay)
    raise AssertionError("unreachable")
