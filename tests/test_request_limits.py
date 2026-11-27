import asyncio
import json

from fastapi.testclient import TestClient

from app import request_limits
from app.config import Settings
from app.main import app
from app.request_limits import RequestBodyLimitMiddleware


def test_content_length_over_comment_limit_is_rejected():
    client = TestClient(app)
    body = json.dumps({"author": "x", "content": "a" * 40_000})

    response = client.post(
        "/api/shares/not-a-real-token/comments",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert "限制" in response.json()["detail"]


def test_chunked_body_without_content_length_is_rejected():
    received = 0

    async def inner(scope, receive, send):
        nonlocal received
        while True:
            message = await receive()
            received += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RequestBodyLimitMiddleware(inner)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/shares/token/comments",
        "raw_path": b"/api/shares/token/comments",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"x" * 40_000, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))

    assert received == 0
    assert sent[0]["status"] == 413


def test_versioned_routes_use_the_same_specific_limits(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path,
        max_upload_mb=500,
        max_request_mb=16,
        max_comment_body_kb=32,
    )
    monkeypatch.setattr(request_limits, "get_settings", lambda: settings)

    assert request_limits._limit_for("/api/v1/projects", "POST", settings) > 16 * 1024 * 1024
    assert (
        request_limits._limit_for(
            "/api/v1/shares/token/comments",
            "POST",
            settings,
        )
        == 32 * 1024
    )


def test_invalid_content_length_is_rejected_before_inner_app():
    async def inner(_scope, _receive, _send):
        raise AssertionError("inner application must not run")

    middleware = RequestBodyLimitMiddleware(inner)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/projects",
        "raw_path": b"/api/projects",
        "query_string": b"",
        "headers": [(b"content-length", b"not-a-number")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))

    assert sent[0]["status"] == 400
