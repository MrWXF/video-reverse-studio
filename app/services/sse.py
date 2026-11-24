import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import Request

from ..db import SessionLocal
from ..models import Job, PromptProject

_TERMINAL = {"done", "failed", "cancelled"}


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def job_event_stream(request: Request, job_id: str) -> AsyncGenerator[str, None]:
    yield "retry: 2500\n\n"
    for _ in range(900):
        if await request.is_disconnected():
            return
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                yield _event("error", {"detail": "任务不存在"})
                return
            payload = {
                "id": job.id,
                "status": job.status,
                "step": job.step,
                "progress": job.progress,
                "error": job.error,
            }
            status = job.status
        yield _event("complete" if status in _TERMINAL else "progress", payload)
        if status in _TERMINAL:
            return
        await asyncio.sleep(1)


async def prompt_event_stream(
    request: Request, project_id: str
) -> AsyncGenerator[str, None]:
    yield "retry: 2500\n\n"
    for _ in range(900):
        if await request.is_disconnected():
            return
        with SessionLocal() as db:
            project = db.get(PromptProject, project_id)
            if project is None:
                yield _event("error", {"detail": "提示词项目不存在"})
                return
            payload = {
                "id": project.id,
                "status": project.status,
                "step": project.step,
                "progress": project.progress,
                "error": project.error,
            }
            status = project.status
        yield _event("complete" if status in _TERMINAL else "progress", payload)
        if status in _TERMINAL:
            return
        await asyncio.sleep(1)
