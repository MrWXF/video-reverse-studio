import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Project, Shot
from app.services import prompt_generation


@pytest.fixture
def reference_client(tmp_path, monkeypatch):
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

    source = tmp_path / "reference.mp4"
    source.write_bytes(b"reference")
    with testing_session() as db:
        db.add(
            Project(
                id="ref-project",
                title="参考竖屏广告",
                source_path=str(source),
                status="done",
                duration=9.0,
                width=1080,
                height=1920,
                fps=24.0,
            )
        )
        analyses = [
            {
                "shot_type": "特写",
                "camera_movement": "缓慢推镜",
                "subject": "咖啡杯",
                "scene": "清晨厨房",
                "visual_style": "warm editorial commercial",
                "lighting": "暖色轮廓光",
                "color_palette": ["#f59e0b", "#1c1917", "#fef3c7"],
                "prompt": "close-up of a coffee cup",
            },
            {
                "shot_type": "中景",
                "camera_movement": "横移",
                "subject": "人物",
                "scene": "窗边",
                "visual_style": "warm editorial commercial",
                "lighting": "自然柔光",
                "color_palette": ["#f59e0b", "#e2e8f0"],
                "prompt": "medium shot of a person",
            },
            {
                "shot_type": "全景",
                "camera_movement": "固定",
                "subject": "餐桌",
                "scene": "厨房",
                "visual_style": "warm editorial commercial",
                "lighting": "侧逆光",
                "color_palette": ["#1c1917", "#fef3c7"],
                "prompt": "wide shot of a table",
            },
        ]
        for index, analysis in enumerate(analyses, start=1):
            db.add(
                Shot(
                    id=index,
                    project_id="ref-project",
                    index=index,
                    start_s=(index - 1) * 3.0,
                    end_s=index * 3.0,
                    origin="filmed",
                    confidence=0.9,
                    analysis=analysis,
                )
            )
        db.add(
            Project(
                id="pending-project",
                title="分析中",
                source_path=str(source),
                status="running",
            )
        )
        db.commit()

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), testing_session
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_reference_context_exposes_prefill_values(reference_client):
    client, _ = reference_client

    response = client.get("/api/projects/ref-project/reference-context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["suggested"]["aspect_ratio"] == "9:16"
    assert payload["suggested"]["shot_count"] == 3
    assert payload["reference"]["recipe"]["pacing"] == "medium"


def test_prompt_project_inherits_reference_structure(reference_client):
    client, _ = reference_client

    created = client.post(
        "/api/prompt-projects",
        json={
            "title": "新产品短片",
            "idea": "用一个新产品的清晨使用场景替换原片内容",
            "reference_project_id": "ref-project",
            "reference_mode": "structure",
            "duration_s": 9.0,
            "shot_count": 3,
        },
    )

    assert created.status_code == 201
    project_id = created.json()["prompt_project_id"]
    detail = client.get(f"/api/prompt-projects/{project_id}").json()
    assert detail["source_project_id"] == "ref-project"
    assert detail["reference_mode"] == "structure"
    assert detail["reference"]["title"] == "参考竖屏广告"
    assert detail["reference"]["recipe"]["shots"][0]["shot_type"] == "特写"
    assert [shot["source_shot_index"] for shot in detail["plan"]["shots"]] == [1, 2, 3]
    assert detail["plan"]["shots"][0]["shot_type"] == "特写"
    assert detail["plan"]["shots"][1]["camera_movement"] == "横移"


def test_prompt_project_inherits_reference_visual_style_in_prompts(reference_client):
    client, _ = reference_client

    created = client.post(
        "/api/prompt-projects",
        json={
            "idea": "用新的生活方式场景创作短片",
            "reference_project_id": "ref-project",
            "reference_mode": "style",
            "shot_count": 2,
        },
    )

    detail = client.get(
        f"/api/prompt-projects/{created.json()['prompt_project_id']}"
    ).json()

    assert detail["plan"]["global_style"] == "warm editorial commercial"
    assert all(
        "warm editorial commercial" in shot["prompt"]
        for shot in detail["plan"]["shots"]
    )


def test_reverse_project_lists_derived_prompt_projects(reference_client):
    client, _ = reference_client
    client.post(
        "/api/prompt-projects",
        json={
            "idea": "基于参考片的新创意",
            "reference_project_id": "ref-project",
            "reference_mode": "style",
            "shot_count": 2,
        },
    )

    detail = client.get("/api/projects/ref-project").json()

    assert len(detail["prompt_projects"]) == 1
    assert detail["prompt_projects"][0]["reference_mode"] == "style"


def test_prompt_reference_validation(reference_client):
    client, _ = reference_client

    missing = client.post(
        "/api/prompt-projects",
        json={"idea": "新创意", "reference_project_id": "missing"},
    )
    pending = client.post(
        "/api/prompt-projects",
        json={"idea": "新创意", "reference_project_id": "pending-project"},
    )

    assert missing.status_code == 404
    assert pending.status_code == 409
