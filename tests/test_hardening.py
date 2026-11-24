import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services import capacity, sse
from app.services.redaction import redact_text
from app.services.retry import RetryableServiceError, retry_call
from app.services.uploads import (
    UploadTooLargeError,
    UploadValidationError,
    safe_filename,
    save_validated_upload,
    validate_video_header,
)


class _Upload:
    def __init__(self, content: bytes):
        self.file = io.BytesIO(content)


def test_retry_call_retries_retryable_errors_with_backoff():
    calls = 0
    delays: list[float] = []

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("temporary")
        return "ok"

    result = retry_call(
        operation,
        attempts=3,
        base_delay=0.5,
        max_delay=2.0,
        sleep=delays.append,
    )

    assert result == "ok"
    assert calls == 3
    assert delays == [0.5, 1.0]


def test_retry_call_does_not_retry_permanent_errors():
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        retry_call(operation, attempts=3, sleep=lambda _delay: None)
    assert calls == 1


def test_retryable_service_error_is_retried():
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RetryableServiceError("upstream")
        return 1

    assert retry_call(operation, attempts=2, sleep=lambda _delay: None) == 1


def test_redaction_removes_paths_and_keys(tmp_path):
    settings = Settings(data_dir=tmp_path, llm_api_key="sk-verysecret123")
    text = redact_text(
        f"failed at {tmp_path}/projects/a.mp4?api_key=abc password=hunter2 "
        "Authorization: Bearer abcdefgh12345678 sk-verysecret123",
        settings,
    )

    assert str(tmp_path) not in text
    assert "sk-verysecret123" not in text
    assert "hunter2" not in text
    assert "<DATA_DIR>" in text


def test_upload_signature_validation_and_streaming(tmp_path):
    validate_video_header(".mp4", b"\x00\x00\x00\x18ftypmp42more")
    validate_video_header(".webm", b"\x1aE\xdf\xa3rest-of-file")
    validate_video_header(".avi", b"RIFF\x00\x00\x00\x00AVI LIST")

    with pytest.raises(UploadValidationError):
        validate_video_header(".mp4", b"not-a-video-at-all")
    with pytest.raises(UploadValidationError):
        validate_video_header(".mp4", b"short")

    target = tmp_path / "source.mp4"
    written = save_validated_upload(
        _Upload(b"\x00\x00\x00\x18ftypmp42payload"),
        target,
        1024,
    )
    assert written == target.stat().st_size
    with pytest.raises(UploadTooLargeError):
        save_validated_upload(
            _Upload(b"\x00\x00\x00\x18ftypmp42payload"),
            tmp_path / "large.mp4",
            8,
        )


def test_safe_filename_strips_paths_and_control_characters():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename(" ..\\evil\x00.mp4 ") == "evil.mp4"


def test_capacity_rejects_over_limit_and_releases_cleanly():
    capacity.reset_for_tests()
    assert capacity.acquire_job(1)
    assert not capacity.has_capacity(1)
    assert not capacity.acquire_job(1)
    capacity.release_job()
    assert capacity.has_capacity(1)


def test_sse_connection_limit_is_bounded():
    sse.reset_for_tests()
    assert sse._acquire_stream(1)
    assert not sse._acquire_stream(1)
    sse._release_stream()
    assert sse.active_streams() == 0


def test_sse_emits_heartbeat_and_enforces_lifetime(monkeypatch):
    settings = Settings(sse_heartbeat_s=2.0, sse_max_seconds=30.0)
    ticks = iter([0.0, 0.1, 20.0, 20.1, 40.0, 40.0])
    monkeypatch.setattr(sse, "get_settings", lambda: settings)
    monkeypatch.setattr(
        sse,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks)),
    )

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(sse.asyncio, "sleep", no_sleep)

    class FakeRequest:
        async def is_disconnected(self):
            return False

    request = FakeRequest()

    async def collect():
        return [
            event
            async for event in sse._stream(
                request,
                lambda: {"status": "running"},
                "任务不存在",
            )
        ]

    sse.reset_for_tests()
    events = asyncio.run(collect())

    assert any("event: heartbeat" in event for event in events)
    assert any("最大生命周期" in event for event in events)
    assert sse.active_streams() == 0


def test_request_trace_version_alias_and_static_cache_headers(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)
    try:
        health = client.get("/healthz", headers={"X-Request-ID": "trace-test-1"})
        assert health.status_code == 200
        assert health.headers["x-request-id"] == "trace-test-1"
        assert health.headers["x-api-version"] == "v1"

        versioned = client.get("/api/v1/model-profiles")
        assert versioned.status_code == 200
        assert versioned.json()

        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "/api/v1/projects" in openapi.json()["paths"]

        static = client.get("/static/style.css")
        assert static.status_code == 200
        assert "max-age=3600" in static.headers["cache-control"]
    finally:
        get_settings.cache_clear()
