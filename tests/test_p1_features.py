import json
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
from app.models import Project, Shot
from app.services import prompt_generation


@pytest.fixture
def studio_client(tmp_path, monkeypatch):
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

    source = tmp_path / "reference.mp4"
    source.write_bytes(b"reference")
    analyses = [
        {
            "shot_type": "特写",
            "camera_movement": "缓慢推镜",
            "subject": "咖啡杯",
            "scene": "清晨厨房",
            "visual_style": "warm editorial commercial",
            "lighting": "暖色轮廓光",
            "color_palette": ["#f59e0b", "#1c1917"],
            "prompt": "close-up of a coffee cup",
        },
        {
            "shot_type": "全景",
            "camera_movement": "横移",
            "subject": "餐桌",
            "scene": "窗边",
            "visual_style": "warm editorial commercial",
            "lighting": "自然柔光",
            "color_palette": ["#f59e0b", "#fef3c7"],
            "prompt": "wide shot of a dining table",
        },
    ]
    with testing_session() as db:
        db.add(
            Project(
                id="reference-project",
                title="参考广告",
                source_path=str(source),
                status="done",
                duration=8.0,
                width=1080,
                height=1920,
                fps=24.0,
            )
        )
        for index, analysis in enumerate(analyses, start=1):
            db.add(
                Shot(
                    id=index,
                    project_id="reference-project",
                    index=index,
                    start_s=(index - 1) * 4.0,
                    end_s=index * 4.0,
                    origin="filmed",
                    confidence=0.9,
                    analysis=analysis,
                )
            )
        db.commit()

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app), testing_session, settings
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def create_prompt(client, **overrides):
    payload = {
        "title": "产品新片",
        "idea": "用新产品替换参考片里的主体",
        "duration_s": 8.0,
        "shot_count": 2,
        "reference_project_id": "reference-project",
        "reference_mode": "structure",
        "entity_bible": {
            "products": [
                {
                    "name": "Lumen Bottle",
                    "appearance": "matte blue flask with a copper cap",
                    "must_keep": ["copper cap"],
                }
            ],
            "scenes": [{"name": "sunlit studio", "description": "pale stone counter"}],
            "consistency_rules": ["keep the copper cap visible in every shot"],
        },
    }
    payload.update(overrides)
    response = client.post("/api/prompt-projects", json=payload)
    assert response.status_code == 201
    return response.json()["prompt_project_id"]


def test_reverse_shot_edit_rebuilds_recipe_files(studio_client, tmp_path):
    client, _, _ = studio_client

    response = client.patch(
        "/api/projects/reference-project/shots/1",
        json={
            "subject": "手冲咖啡壶",
            "shot_type": "近景",
            "transcript": "新旁白",
            "color_palette": ["#111111", "#eeeeee"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["subject"] == "手冲咖啡壶"
    assert payload["transcript"] == "新旁白"
    recipe = client.get("/api/projects/reference-project/recipe?format=json").json()
    assert recipe["shots"][0]["subject"] == "手冲咖啡壶"
    assert recipe["shots"][0]["shot_type"] == "近景"
    output = tmp_path / "projects" / "reference-project" / "output"
    assert (output / "video.md").exists()
    assert "手冲咖啡壶" in (output / "video.md").read_text(encoding="utf-8")


def test_entity_bible_is_used_by_mock_prompts(studio_client):
    client, _, _ = studio_client
    project_id = create_prompt(client)

    detail = client.get(f"/api/prompt-projects/{project_id}").json()

    assert detail["entity_bible"]["products"][0]["name"] == "Lumen Bottle"
    assert detail["version_count"] == 1
    assert "Lumen Bottle" in detail["plan"]["shots"][0]["prompt"]
    assert "sunlit studio" in detail["plan"]["shots"][0]["prompt"]
    assert "keep the copper cap visible" in detail["plan"]["shots"][0]["prompt"]


def test_prompt_shot_edit_lock_regenerate_and_restore(studio_client):
    client, _, _ = studio_client
    project_id = create_prompt(client)
    original = client.get(f"/api/prompt-projects/{project_id}").json()
    original_prompt = original["plan"]["shots"][0]["prompt"]

    edited = client.patch(
        f"/api/prompt-projects/{project_id}/shots/1",
        json={
            "prompt": "LOCKED PROMPT: hero bottle on a stone counter",
            "subject": "hero bottle",
            "locked_fields": ["prompt", "shot_type"],
        },
    )
    assert edited.status_code == 200
    edited_shot = edited.json()["plan"]["shots"][0]
    assert edited_shot["prompt"] == "LOCKED PROMPT: hero bottle on a stone counter"
    assert edited_shot["locked_fields"] == ["prompt", "shot_type"]

    regenerated = client.post(
        f"/api/prompt-projects/{project_id}/shots/1/regenerate"
    )
    assert regenerated.status_code == 200
    regenerated_shot = regenerated.json()["plan"]["shots"][0]
    assert regenerated_shot["prompt"] == "LOCKED PROMPT: hero bottle on a stone counter"
    assert regenerated_shot["shot_type"] == edited_shot["shot_type"]
    assert regenerated_shot["duration"] == edited_shot["duration"]

    versions = client.get(f"/api/prompt-projects/{project_id}/versions").json()
    assert [item["version"] for item in versions[:3]] == [3, 2, 1]
    initial = next(item for item in versions if item["version"] == 1)
    restored = client.post(
        f"/api/prompt-projects/{project_id}/versions/{initial['id']}/restore"
    )
    assert restored.status_code == 200
    assert restored.json()["plan"]["shots"][0]["prompt"] == original_prompt
    assert restored.json()["version_count"] == 4


def test_entity_bible_update_and_reference_comparison(studio_client):
    client, _, _ = studio_client
    project_id = create_prompt(client)

    updated = client.patch(
        f"/api/prompt-projects/{project_id}/entity-bible",
        json={
            "characters": [{"name": "Mia", "appearance": "short black hair"}],
            "products": [{"name": "Lumen Bottle"}],
            "wardrobe": [{"name": "red trench coat"}],
            "scenes": [{"name": "sunlit studio"}],
            "consistency_rules": ["Mia always wears the red coat"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["entity_bible"]["characters"][0]["name"] == "Mia"

    comparison = client.get(f"/api/prompt-projects/{project_id}/comparison")
    assert comparison.status_code == 200
    payload = comparison.json()
    assert payload["mode"] == "structure"
    assert payload["summary"]["mapped_shots"] == 2
    assert payload["summary"]["structure_match"] >= 0.5
    assert payload["shots"][0]["reference"]["shot_type"] == "特写"
    assert payload["shots"][0]["generated"]["shot_type"] == "特写"


def test_version_restore_validates_version_ownership(studio_client):
    client, _, _ = studio_client
    first = create_prompt(client, title="方案一")
    second = create_prompt(client, title="方案二")
    version = client.get(f"/api/prompt-projects/{first}/versions").json()[0]

    response = client.post(
        f"/api/prompt-projects/{second}/versions/{version['id']}/restore"
    )

    assert response.status_code == 404
