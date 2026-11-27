"""HTTP Basic authentication helpers and fail-closed middleware."""

import base64
import secrets
import threading
import time
from collections import deque

from starlette.datastructures import Headers
from starlette.responses import Response

from .config import get_settings

_UNAUTHORIZED_HEADERS = {
    "WWW-Authenticate": 'Basic realm="ReelReverse", charset="UTF-8"',
    "Cache-Control": "no-store",
}

_failure_lock = threading.Lock()
_failures: dict[str, deque[float]] = {}


def _client_key(scope) -> str:
    """Return a bounded client identifier used for authentication throttling."""
    client = scope.get("client")
    return str(client[0])[:80] if client else "unknown"


def _prune_failures(entries: deque[float], now: float, window_s: int) -> None:
    """Discard authentication failures outside the sliding window."""
    cutoff = now - window_s
    while entries and entries[0] <= cutoff:
        entries.popleft()


def _retry_after(client_key: str, limit: int, window_s: int) -> int:
    """Return seconds until authentication can be retried, or zero when allowed."""
    now = time.monotonic()
    with _failure_lock:
        entries = _failures.setdefault(client_key, deque())
        _prune_failures(entries, now, window_s)
        if len(entries) < limit:
            return 0
        return max(1, int(entries[0] + window_s - now) + 1)


def _record_failure(client_key: str, window_s: int) -> None:
    """Record one failed authentication attempt for the client."""
    now = time.monotonic()
    with _failure_lock:
        entries = _failures.setdefault(client_key, deque())
        _prune_failures(entries, now, window_s)
        entries.append(now)


def _clear_failures(client_key: str) -> None:
    """Clear failure history after a successful authentication."""
    with _failure_lock:
        _failures.pop(client_key, None)


def reset_auth_failures_for_tests() -> None:
    """Reset the process-local authentication failure tracker."""
    with _failure_lock:
        _failures.clear()


def decode_basic_auth(header: str) -> tuple[str, str] | None:
    """Decode an HTTP Basic header into username/password, or return ``None``."""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        return None
    try:
        decoded = base64.b64decode(token, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return username, password


def verify_basic_auth(header: str, username: str, password: str) -> bool:
    """Compare supplied Basic credentials in constant time."""
    credentials = decode_basic_auth(header)
    if credentials is None:
        return False
    supplied_username, supplied_password = credentials
    user_ok = secrets.compare_digest(
        supplied_username.encode("utf-8"), username.encode("utf-8")
    )
    password_ok = secrets.compare_digest(
        supplied_password.encode("utf-8"), password.encode("utf-8")
    )
    return user_ok and password_ok


_MISSING_PASSWORD_MESSAGE = (
    "服务尚未配置 APP_PASSWORD。为防止误将无认证服务暴露到网络，"
    "默认拒绝访问；仅本地开发可显式设置 ALLOW_INSECURE_NO_AUTH=true。"
)


class BasicAuthMiddleware:
    """Require HTTP Basic credentials unless authentication is explicitly disabled.

    Health checks, static files, and token-scoped share endpoints remain public.
    An empty ``APP_PASSWORD`` is treated as a configuration error rather than an
    invitation to serve the application without authentication.
    """

    def __init__(self, app):
        """Store the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """Allow public paths or require valid Basic credentials."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        public_path = (
            scope["path"] == "/healthz"
            or scope["path"].startswith("/share/")
            or scope["path"].startswith("/api/shares/")
            or scope["path"].startswith("/static/")
        )
        if public_path:
            await self.app(scope, receive, send)
            return

        if not settings.app_password:
            if settings.allow_insecure_no_auth:
                await self.app(scope, receive, send)
                return
            response = Response(
                _MISSING_PASSWORD_MESSAGE,
                status_code=503,
                headers=_UNAUTHORIZED_HEADERS,
            )
            await response(scope, receive, send)
            return

        client_key = _client_key(scope)
        retry_after = _retry_after(
            client_key,
            settings.auth_max_failures,
            settings.auth_failure_window_s,
        )
        if retry_after:
            response = Response(
                "Too Many Requests",
                status_code=429,
                headers={
                    **_UNAUTHORIZED_HEADERS,
                    "Retry-After": str(retry_after),
                },
            )
            await response(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if verify_basic_auth(
            headers.get("authorization", ""),
            settings.app_username,
            settings.app_password,
        ):
            _clear_failures(client_key)
            await self.app(scope, receive, send)
            return

        _record_failure(client_key, settings.auth_failure_window_s)
        response = Response(
            "Unauthorized",
            status_code=401,
            headers=_UNAUTHORIZED_HEADERS,
        )
        await response(scope, receive, send)
