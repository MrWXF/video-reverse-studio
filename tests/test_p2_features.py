import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.api import prompt_routes, routes
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Job, Project, PromptProject, PromptShare
from app.schemas import PromptPlan, PromptShot
from app.services import delivery_review, media, model_profiles, prompt_generation, sse


@pytest.fixture
def p2_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    settings = Settings(
        data_dir=tmp_path,
        app_password="",
        llm_provider="mock",
        llm_api_key="",
    )
    for module in (security, prompt_generation, prompt_routes, routes):
        monkeypatch.setattr(module, "get_settings", lambda: settings)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(prompt_generation, "SessionLocal", testing_session)
    monkeypatch.setattr(sse, "SessionLocal", testing_session)

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), testing_session, settings, tmp_path
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def create_prompt(client: TestClient, **overrides) -> str:
    payload = {
        "title": "可交付广告",
        "idea": "清晨厨房里的气泡水产品广告",
        "target_model": "veo",
        "duration_s": 8.0,
        "aspect_ratio": "9:16",
        "shot_count": 2,
        "style": "clean editorial commercial",
        "entity_bible": {
            "products": [
                {
                    "name": "Lumen Bottle",
                    "appearance": "matte blue flask with a copper cap",
                    "must_keep": ["copper cap"],
                }
            ],
            "consistency_rules": ["keep the copper cap visible in every shot"],
        },
    }
    payload.update(overrides)
    response = client.post("/api/prompt-projects", json=payload)
    assert response.status_code == 201
    return response.json()["prompt_project_id"]


def test_model_profiles_and_over_limit_warnings(p2_client):
    client, _, _, _ = p2_client
    profiles = client.get("/api/model-profiles")

    assert profiles.status_code == 200
    options = {item["id"]: item for item in profiles.json()}
    assert {"generic", "veo", "sora", "runway", "kling", "luma", "pika"} <= set(options)
    assert options["veo"]["max_shot_seconds"] == 8.0
    assert model_profiles.get_model_profile("Gen-3")["id"] == "runway"
    assert model_profiles.get_model_profile("unknown-platform")["id"] == "generic"

    plan = PromptPlan(
        target_model="veo",
        target_profile=model_profiles.get_model_profile("veo"),
        duration_s=12.0,
        aspect_ratio="21:9",
        shots=[
            PromptShot(
                index=1,
                duration=1.0,
                prompt="x" * 1300,
                negative_prompt="n" * 600,
            )
        ],
    )
    warnings = model_profiles.validate_prompt_plan(plan, plan.duration_s)
    text = "\n".join(warnings)
    assert "1200" in text
    assert "500" in text
    assert "21:9" in text
    assert "建议时长" in text


def test_prompt_zip_contains_delivery_assets(p2_client):
    client, _, _, _ = p2_client
    project_id = create_prompt(client)

    detail = client.get(f"/api/prompt-projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "done"

    response = client.get(f"/api/prompt-projects/{project_id}/export/zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "prompt-" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert {
            "README.md",
            "prompt-plan.md",
            "prompt-plan.json",
            "shots.csv",
            "shots.srt",
            "entity-bible.json",
            "versions.json",
        } <= names
        assert "Lumen Bottle" in archive.read("entity-bible.json").decode("utf-8")
        csv_text = archive.read("shots.csv").decode("utf-8")
        assert "source_shot_index" in csv_text
        assert "locked_fields" in csv_text


def test_share_permissions_comments_revoke_and_expiry(p2_client):
    client, testing_session, _, _ = p2_client
    project_id = create_prompt(client)

    readonly = client.post(
        f"/api/prompt-projects/{project_id}/shares",
        json={"permission": "read", "expires_in_days": 7},
    )
    assert readonly.status_code == 201
    readonly_share = readonly.json()
    assert readonly_share["permission"] == "read"
    assert readonly_share["expires_at"]

    shared = client.get(f"/api/shares/{readonly_share['token']}")
    assert shared.status_code == 200
    payload = shared.json()
    assert payload["read_only"] is True
    assert payload["share"]["permission"] == "read"
    assert payload["plan"]["shots"]

    blocked = client.post(
        f"/api/shares/{readonly_share['token']}/comments",
        json={"author": "访客", "content": "这个镜头可以再近一点"},
    )
    assert blocked.status_code == 403

    comments = client.post(
        f"/api/prompt-projects/{project_id}/shares",
        json={"permission": "comment"},
    ).json()
    created = client.post(
        f"/api/shares/{comments['token']}/comments",
        json={"author": "客户", "content": "第二镜节奏很好"},
    )
    assert created.status_code == 201
    listed = client.get(f"/api/shares/{comments['token']}/comments")
    assert listed.status_code == 200
    assert listed.json()[0]["author"] == "客户"

    revoked = client.delete(
        f"/api/prompt-projects/{project_id}/shares/{readonly_share['id']}"
    )
    assert revoked.status_code == 200
    assert client.get(f"/api/shares/{readonly_share['token']}").status_code == 404

    expired = client.post(
        f"/api/prompt-projects/{project_id}/shares",
        json={"permission": "read"},
    ).json()
    with testing_session() as db:
        item = db.get(PromptShare, expired["id"])
        item.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    assert client.get(f"/api/shares/{expired['token']}").status_code == 410


def test_share_page_and_api_remain_public_with_basic_auth(p2_client, monkeypatch):
    client, _, settings, _ = p2_client
    project_id = create_prompt(client)
    share = client.post(
        f"/api/prompt-projects/{project_id}/shares",
        json={"permission": "read"},
    ).json()

    protected = Settings(
        data_dir=settings.data_dir,
        app_username="admin",
        app_password="secret",
        llm_provider="mock",
        llm_api_key="",
    )
    monkeypatch.setattr(security, "get_settings", lambda: protected)

    assert client.get("/").status_code == 401
    page = client.get(f"/share/{share['token']}")
    assert page.status_code == 200
    assert share["token"] in page.text
    assert client.get(f"/api/shares/{share['token']}").status_code == 200


def test_delivery_review_scores_shots_and_palette(p2_client, monkeypatch, tmp_path):
    _, _, _, data_dir = p2_client
    video = data_dir / "delivery.mp4"
    video.write_bytes(b"review-video")
    plan = PromptPlan(
        duration_s=8.0,
        aspect_ratio="9:16",
        shots=[
            PromptShot(index=1, duration=4.0, color_palette=["#f59e0b", "#1c1917"]),
            PromptShot(index=2, duration=4.0, color_palette=["#f59e0b", "#fef3c7"]),
        ],
    )

    monkeypatch.setattr(
        media,
        "probe",
        lambda path, settings: media.VideoMeta(
            duration=8.0,
            width=1080,
            height=1920,
            fps=24.0,
        ),
    )
    monkeypatch.setattr(media, "detect_shots", lambda path, meta, settings: [(0.0, 4.0), (4.0, 8.0)])
    monkeypatch.setattr(media, "resolve_ffmpeg", lambda configured: "ffmpeg")
    monkeypatch.setattr(delivery_review, "_average_color", lambda ffmpeg, path, ts: "#f59e0b")

    result = delivery_review.evaluate_delivery(video, plan, Settings(data_dir=data_dir))

    assert result["summary"]["expected_shots"] == 2
    assert result["summary"]["actual_shots"] == 2
    assert result["summary"]["execution_score"] >= 0.9
    assert 0.7 <= result["summary"]["style_score"] < 1.0
    assert result["summary"]["overall_score"] >= 0.85
    assert result["shots"][0]["execution_score"] >= 0.9
    assert result["style"]["actual_palette"] == ["#f59e0b"]
    assert "不等同于视觉语义审核" in result["warnings"][-1]


def test_review_upload_route_and_delete(p2_client, monkeypatch):
    client, _, _, _ = p2_client
    project_id = create_prompt(client)
    monkeypatch.setattr(prompt_routes.delivery_review, "run_delivery_review", lambda review_id: None)

    response = client.post(
        f"/api/prompt-projects/{project_id}/reviews",
        files={"file": ("delivery.mp4", b"fake-video", "video/mp4")},
    )
    assert response.status_code == 202
    review = response.json()
    assert review["status"] == "queued"
    assert review["filename"] == "delivery.mp4"

    listed = client.get(f"/api/prompt-projects/{project_id}/reviews")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == review["id"]

    deleted = client.delete(f"/api/prompt-projects/{project_id}/reviews/{review['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/prompt-projects/{project_id}/reviews").json() == []


def test_prompt_and_reverse_job_cancel_with_terminal_sse(p2_client):
    client, testing_session, _, data_dir = p2_client
    project_id = create_prompt(client)

    prompt_events = client.get(f"/api/prompt-projects/{project_id}/events")
    assert prompt_events.status_code == 200
    assert "event: complete" in prompt_events.text
    assert '"status": "done"' in prompt_events.text

    with testing_session() as db:
        db.add(
            PromptProject(
                id="running-prompt",
                title="正在生成的方案",
                status="running",
                step="planning",
                brief_json={"idea": "正在生成"},
            )
        )
        db.add(
            Project(
                id="running-project",
                title="正在分析的项目",
                source_path=str(data_dir / "source.mp4"),
                status="running",
            )
        )
        db.add(
            Job(
                id="running-job",
                project_id="running-project",
                status="running",
                step="analyzing",
                progress=0.4,
            )
        )
        db.commit()

    cancelled_prompt = client.post("/api/prompt-projects/running-prompt/cancel")
    assert cancelled_prompt.status_code == 202
    assert cancelled_prompt.json()["status"] == "cancelled"
    assert client.post("/api/prompt-projects/running-prompt/cancel").status_code == 409

    cancelled_project = client.post("/api/projects/running-project/cancel")
    assert cancelled_project.status_code == 202
    assert cancelled_project.json()["status"] == "cancelled"

    job_events = client.get("/api/jobs/running-job/events")
    assert job_events.status_code == 200
    assert "event: complete" in job_events.text
    assert '"status": "cancelled"' in job_events.text
