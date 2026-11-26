"""Request-scoped logging context, structured JSON logs, and request-id middleware."""

import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .services.redaction import redact_text

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def current_request_id() -> str:
    """Return the request id bound to the current execution context."""
    return request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the active request id to the log record."""
        record.request_id = current_request_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Emit structured, redacted JSON log lines for application and access logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Render one redacted JSON log record."""
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage(), limit=4000),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = redact_text(
                self.formatException(record.exc_info), limit=8000
            )
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Install the JSON stream handler as the single root log handler."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _clean_request_id(value: str | None) -> str:
    """Sanitize a caller-supplied request id or generate a new one."""
    if not value:
        return uuid.uuid4().hex
    cleaned = "".join(char for char in value if char.isalnum() or char in "-_.")[:64]
    return cleaned or uuid.uuid4().hex


class RequestContextMiddleware:
    """Attach request tracing, API version aliasing and cache headers."""

    def __init__(self, app: ASGIApp):
        """Store the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Bind request tracing, rewrite versioned API paths, and log durations."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = _clean_request_id(supplied)
        token = request_id_ctx.set(request_id)
        started = time.monotonic()
        path = scope.get("path", "")
        api_version = "v1"

        if path == "/api/v1" or path.startswith("/api/v1/"):
            scope = dict(scope)
            rewritten = "/api" + path[len("/api/v1") :]
            scope["path"] = rewritten
            scope["raw_path"] = rewritten.encode("latin-1")

        logger = logging.getLogger("app.request")

        async def send_with_headers(message: Message) -> None:
            """Attach tracing/security headers and static-file cache policy."""
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("latin-1")))
                response_headers.append((b"x-api-version", api_version.encode("ascii")))
                response_headers.append((b"x-content-type-options", b"nosniff"))
                if path.startswith("/static/"):
                    response_headers.append(
                        (b"cache-control", b"public, max-age=3600, stale-while-revalidate=86400")
                    )
                message["headers"] = response_headers
            await send(message)

        logger.info(
            "request_started method=%s path=%s",
            scope.get("method", ""),
            path,
        )
        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            logger.info(
                "request_finished method=%s path=%s duration_ms=%.1f",
                scope.get("method", ""),
                path,
                (time.monotonic() - started) * 1000,
            )
            request_id_ctx.reset(token)
