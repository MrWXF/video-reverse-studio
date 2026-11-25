from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.api import generation_routes, insight_routes, prompt_routes, routes
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import GenerationJob, PromptProject
from app.services import capacity, generation, generation_adapters, prompt_generation


@pytest.fixture
def generation_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    settings = Settings(
        data_dir=tmp_path,
        app_password="",
        llm_provider="mock",
        llm_api_key="",
        video_provider="mock",
        video_model="mock-v1",
        generation_retry_attempts=1,
    )
    for module in (
        security,
        prompt_generation,
        prompt_routes,
        routes,
        insight_routes,
        generation,
        generation_routes,
    ):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(generation_adapters, "resolve_ffmpeg", lambda _: None)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(prompt_generation, "SessionLocal", testing_session)
    monkeypatch.setattr(generation, "SessionLocal", testing_session)
    capacity.reset_for_tests()

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), testing_session, settings
    app.dependency_overrides.clear()
    capacity.reset_for_tests()
    get_settings.cache_clear()


def create_prompt_project(client: TestClient) -> str:
    response = client.post(
        "/api/prompt-projects",
        json={
            "title": "Mock generation test",
            "idea": "A calm coffee commercial in a bright kitchen",
            "target_model": "veo",
            "duration_s": 8.0,
            "aspect_ratio": "16:9",
            "shot_count": 2,
            "style": "warm commercial",
            "mood": "calm",
            "negative_prompt": "text, watermark",
        },
    )
    assert response.status_code == 201
    return response.json()["prompt_project_id"]


def test_generation_mock_closed_loop(generation_client, tmp_path):
    client, _, _ = generation_client
    project_id = create_prompt_project(client)

    capabilities = client.get("/api/generation/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["provider"] == "mock"
    assert capabilities.json()["ready"] is True
    assert capabilities.json()["credential_configured"] is False

    created = client.post(
        f"/api/prompt-projects/{project_id}/generation-jobs",
        json={"shot_indices": [1], "aspect_ratio": "16:9"},
    )
    assert created.status_code == 202
    job_id = created.json()["id"]

    detail = client.get(f"/api/generation-jobs/{job_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["status"] == "succeeded"
    assert payload["progress"] == 1.0
    assert len(payload["result"]["shots"]) == 1
    shot = payload["result"]["shots"][0]
    assert shot["shot_index"] == 1
    assert shot["status"] == "succeeded"
    assert shot["media_type"] == "image/svg+xml"
    assert "filename" not in shot
    assert shot["download_url"].endswith("/shots/1/video")

    media = client.get(shot["download_url"])
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/svg+xml")
    assert b"MOCK OUTPUT" in media.content
    assert list((tmp_path / "generations" / project_id / job_id).glob("shot-01.svg"))

    listed = client.get(f"/api/prompt-projects/{project_id}/generation-jobs")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [job_id]


def test_generation_idempotency_and_cancel(generation_client):
    client, testing_session, _ = generation_client
    project_id = create_prompt_project(client)
    body = {
        "shot_indices": [1, 2],
        "aspect_ratio": "16:9",
        "idempotency_key": "generation-request-1",
    }
    first = client.post(f"/api/prompt-projects/{project_id}/generation-jobs", json=body)
    second = client.post(f"/api/prompt-projects/{project_id}/generation-jobs", json=body)
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["reused"] is True

    with testing_session() as db:
        queued = GenerationJob(
            id="queued-job",
            prompt_project_id=project_id,
            provider="mock",
            model="mock-v1",
            status="queued",
            step="queued",
            request_json={"shot_indices": [1]},
        )
        db.add(queued)
        db.commit()

    cancelled = client.post("/api/generation-jobs/queued-job/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.post("/api/generation-jobs/queued-job/cancel").status_code == 409


def test_generation_rejects_incomplete_plan_and_bad_shot(generation_client):
    client, testing_session, _ = generation_client
    with testing_session() as db:
        db.add(
            PromptProject(
                id="running-project",
                title="Running",
                brief_json={"idea": "still generating"},
                status="running",
            )
        )
        db.commit()

    incomplete = client.post(
        "/api/prompt-projects/running-project/generation-jobs",
        json={"shot_indices": []},
    )
    assert incomplete.status_code == 409

    project_id = create_prompt_project(client)
    unknown_shot = client.post(
        f"/api/prompt-projects/{project_id}/generation-jobs",
        json={"shot_indices": [99]},
    )
    assert unknown_shot.status_code == 422


def test_generation_reports_unconnected_provider(generation_client):
    client, _, settings = generation_client
    settings.video_provider = "kling"
    capabilities = client.get("/api/generation/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["ready"] is False

    project_id = create_prompt_project(client)
    response = client.post(
        f"/api/prompt-projects/{project_id}/generation-jobs",
        json={"shot_indices": [1]},
    )
    assert response.status_code == 503
    assert "kling" in response.json()["detail"]


def test_generation_frontend_hooks_are_present():
    root = Path(__file__).resolve().parent.parent
    prompt_js = (root / "app" / "static" / "prompt.js").read_text(encoding="utf-8")
    style = (root / "app" / "static" / "style.css").read_text(encoding="utf-8")

    assert "VIDEO GENERATION" in prompt_js
    assert "data-start-generation" in prompt_js
    assert "data-generate-prompt-shot" in prompt_js
    assert "data-cancel-generation" in prompt_js
    assert "loadGenerationJobs" in prompt_js
    assert ".generation-job" in style
