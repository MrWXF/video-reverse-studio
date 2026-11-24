import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import PromptProject
from app.services import prompt_generation


@pytest.fixture
def prompt_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    get_settings.cache_clear()
    settings = Settings(
        data_dir=tmp_path,
        app_password="",
        llm_provider="mock",
        llm_api_key="",
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(prompt_generation, "get_settings", lambda: settings)

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

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), testing_session, settings
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def create_prompt_project(client, **overrides):
    payload = {
        "title": "清晨咖啡广告",
        "idea": "清晨厨房里的咖啡品牌广告",
        "target_model": "veo",
        "duration_s": 12.0,
        "aspect_ratio": "16:9",
        "shot_count": 3,
        "style": "warm commercial film",
        "mood": "calm and inviting",
        "negative_prompt": "watermark, text",
    }
    payload.update(overrides)
    return client.post("/api/prompt-projects", json=payload)


def test_prompt_project_full_lifecycle(prompt_client):
    client, _, _ = prompt_client

    created = create_prompt_project(client)
    assert created.status_code == 201
    project_id = created.json()["prompt_project_id"]

    listed = client.get("/api/prompt-projects")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == project_id
    assert listed.json()[0]["status"] == "done"
    assert listed.json()[0]["shot_count"] == 3
    assert "plan" not in listed.json()[0]

    detail = client.get(f"/api/prompt-projects/{project_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["status"] == "done"
    assert data["plan"]["target_model"] == "veo"
    assert len(data["plan"]["shots"]) == 3
    assert abs(sum(shot["duration"] for shot in data["plan"]["shots"]) - 12.0) < 0.01

    markdown = client.get(f"/api/prompt-projects/{project_id}/export")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert ".md" in markdown.headers["content-disposition"]
    assert "## 镜头表" in markdown.text
    assert "**Prompt**" in markdown.text

    exported_json = client.get(
        f"/api/prompt-projects/{project_id}/export?format=json"
    )
    assert exported_json.status_code == 200
    assert exported_json.headers["content-type"].startswith("application/json")
    assert ".json" in exported_json.headers["content-disposition"]
    assert len(exported_json.json()["shots"]) == 3


def test_prompt_export_requires_completed_plan(prompt_client):
    client, testing_session, _ = prompt_client
    with testing_session() as db:
        db.add(
            PromptProject(
                id="running-project",
                title="生成中",
                brief_json={"idea": "测试创意"},
                status="running",
            )
        )
        db.commit()

    response = client.get("/api/prompt-projects/running-project/export")

    assert response.status_code == 404


def test_failed_prompt_project_can_regenerate(prompt_client):
    client, testing_session, _ = prompt_client
    with testing_session() as db:
        db.add(
            PromptProject(
                id="failed-project",
                title="失败项目",
                brief_json={
                    "title": "失败项目",
                    "idea": "咖啡广告",
                    "duration_s": 9.0,
                    "shot_count": 3,
                },
                status="failed",
                step="failed",
                error="模型超时",
            )
        )
        db.commit()

    response = client.post("/api/prompt-projects/failed-project/regenerate")

    assert response.status_code == 202
    detail = client.get("/api/prompt-projects/failed-project").json()
    assert detail["status"] == "done"
    assert detail["error"] == ""
    assert len(detail["plan"]["shots"]) == 3


def test_running_prompt_project_rejects_regenerate(prompt_client):
    client, testing_session, _ = prompt_client
    with testing_session() as db:
        db.add(
            PromptProject(
                id="busy-project",
                title="生成中",
                brief_json={"idea": "测试创意"},
                status="running",
            )
        )
        db.commit()

    response = client.post("/api/prompt-projects/busy-project/regenerate")

    assert response.status_code == 409


def test_prompt_project_can_be_deleted(prompt_client):
    client, _, _ = prompt_client
    project_id = create_prompt_project(client).json()["prompt_project_id"]

    deleted = client.delete(f"/api/prompt-projects/{project_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": project_id}
    assert client.get(f"/api/prompt-projects/{project_id}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"idea": "x"},
        {"idea": "咖啡广告", "shot_count": 9},
        {"idea": "咖啡广告", "duration_s": 2.0},
    ],
)
def test_prompt_project_validates_brief(prompt_client, payload):
    client, _, _ = prompt_client

    response = client.post("/api/prompt-projects", json=payload)

    assert response.status_code == 422


def test_prompt_api_requires_auth_when_enabled(prompt_client, monkeypatch):
    client, _, settings = prompt_client
    secured = Settings(
        data_dir=settings.data_dir,
        app_username="alice",
        app_password="secret",
    )
    monkeypatch.setattr(security, "get_settings", lambda: secured)

    assert client.get("/api/prompt-projects").status_code == 401
    assert (
        client.get("/api/prompt-projects", auth=("alice", "secret")).status_code
        == 200
    )
