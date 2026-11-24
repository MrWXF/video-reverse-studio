"""Server-Sent Events status streams with heartbeat and connection limits."""

import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator, Callable

from fastapi import Request

from ..config import get_settings
from ..db import SessionLocal
from ..models import Job, PromptProject

_TERMINAL = {"done", "failed", "cancelled"}
_stream_lock = threading.Lock()
_active_streams = 0


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _acquire_stream(limit: int) -> bool:
    global _active_streams
    with _stream_lock:
        if _active_streams >= max(1, limit):
            return False
        _active_streams += 1
        return True


def _release_stream() -> None:
    global _active_streams
    with _stream_lock:
        _active_streams = max(0, _active_streams - 1)


def active_streams() -> int:
    with _stream_lock:
        return _active_streams


def reset_for_tests() -> None:
    global _active_streams
    with _stream_lock:
        _active_streams = 0


async def _stream(
    request: Request,
    load_payload: Callable[[], dict | None],
    missing_detail: str,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    if not _acquire_stream(settings.sse_max_connections):
        yield _event("error", {"detail": "实时状态连接数已达上限，请稍后重试"})
        return
    try:
        yield "retry: 2500\n\n"
        started = time.monotonic()
        last_heartbeat = started
        while True:
            if await request.is_disconnected():
                return
            payload = load_payload()
            if payload is None:
                yield _event("error", {"detail": missing_detail})
                return
            status = payload["status"]
            yield _event("complete" if status in _TERMINAL else "progress", payload)
            if status in _TERMINAL:
                return
            if time.monotonic() - started >= settings.sse_max_seconds:
                yield _event(
                    "error",
                    {"detail": "实时状态连接已达到最大生命周期，请刷新页面继续查看"},
                )
                return
            await asyncio.sleep(1)
            now = time.monotonic()
            if now - last_heartbeat >= settings.sse_heartbeat_s:
                yield _event(
                    "heartbeat",
                    {"status": status, "elapsed_s": round(now - started, 1)},
                )
                last_heartbeat = now
    finally:
        _release_stream()


def _job_payload(job_id: str) -> dict | None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "status": job.status,
            "step": job.step,
            "progress": job.progress,
            "error": job.error,
        }


def _prompt_payload(project_id: str) -> dict | None:
    with SessionLocal() as db:
        project = db.get(PromptProject, project_id)
        if project is None:
            return None
        return {
            "id": project.id,
            "status": project.status,
            "step": project.step,
            "progress": project.progress,
            "error": project.error,
        }


async def job_event_stream(request: Request, job_id: str) -> AsyncGenerator[str, None]:
    async for event in _stream(request, lambda: _job_payload(job_id), "任务不存在"):
        yield event


async def prompt_event_stream(
    request: Request, project_id: str
) -> AsyncGenerator[str, None]:
    async for event in _stream(
        request,
        lambda: _prompt_payload(project_id),
        "提示词项目不存在",
    ):
        yield event
