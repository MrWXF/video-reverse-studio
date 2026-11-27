"""ASGI middleware that rejects oversized request bodies before they are buffered."""

from __future__ import annotations

import json

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings, get_settings

_BODY_METHODS = {"POST", "PUT", "PATCH"}
_UPLOAD_OVERHEAD_BYTES = 16 * 1024 * 1024


class _BodyTooLarge(Exception):
    """Internal control-flow signal raised after a 413 response has been sent."""


def _limit_for(path: str, method: str, settings: Settings) -> int:
    """Return the byte limit for one request path and method."""
    if method not in _BODY_METHODS:
        return settings.max_request_mb * 1024 * 1024
    if path == "/api/v1" or path.startswith("/api/v1/"):
        path = "/api" + path[len("/api/v1") :]
    path = path.rstrip("/") or "/"
    if path == "/api/projects":
        return settings.max_upload_mb * 1024 * 1024 + _UPLOAD_OVERHEAD_BYTES
    if path.startswith("/api/prompt-projects/") and path.endswith("/reviews"):
        return settings.max_upload_mb * 1024 * 1024 + _UPLOAD_OVERHEAD_BYTES
    if path.startswith("/api/shares/") and path.endswith("/comments"):
        return settings.max_comment_body_kb * 1024
    return settings.max_request_mb * 1024 * 1024


class RequestBodyLimitMiddleware:
    """Enforce a per-route request-body cap for both declared and streamed sizes.

    ``Content-Length`` is checked first so ordinary oversized uploads are rejected
    without reading the body. Wrapping ``receive`` also covers chunked requests or
    clients that provide a forged/missing length header.
    """

    def __init__(self, app: ASGIApp):
        """Store the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject requests whose body exceeds the configured route limit."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        if method not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        path = scope.get("path", "")
        limit = _limit_for(path, method, settings)
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared:
            try:
                declared_length = int(declared)
                if declared_length < 0:
                    await _send_bad_length(send)
                    return
                if declared_length > limit:
                    await _send_413(send, limit)
                    return
            except ValueError:
                await _send_bad_length(send)
                return

        received = 0
        response_started = False

        async def limited_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    if not response_started:
                        await _send_413(limited_send, limit)
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, limited_send)
        except _BodyTooLarge:
            return


async def _send_413(send: Send, limit: int) -> None:
    """Send a JSON 413 response for an oversized body."""
    label = (
        f"{limit / (1024 * 1024):.0f}MB"
        if limit >= 1024 * 1024
        else f"{limit // 1024}KB"
    )
    payload = json.dumps(
        {"detail": f"请求体超过 {label} 限制"},
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


async def _send_bad_length(send: Send) -> None:
    """Send a JSON 400 response for an invalid Content-Length header."""
    payload = json.dumps({"detail": "Content-Length 不合法"}, ensure_ascii=False).encode(
        "utf-8"
    )
    await send(
        {
            "type": "http.response.start",
            "status": 400,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
