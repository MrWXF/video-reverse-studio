from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import security
from app.api import insight_routes, prompt_routes, routes
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Job, Project, PromptProject, Shot
from app.services import cost, prompt_generation


@pytest.fixture
def phase1_client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    settings = Settings(
        data_dir=tmp_path,
        app_password="",
        llm_provider="mock",
        llm_api_key="",
        llm_input_price_per_million=1.0,
        llm_output_price_per_million=2.0,
        cost_currency="USD",
    )
    for module in (security, prompt_generation, prompt_routes, routes, insight_routes):
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
    analysis = {
        "shot_type": "特写",
        "camera_movement": "缓慢推镜",
        "subject": "咖啡杯",
        "scene": "清晨厨房",
        "visual_style": "warm editorial commercial",
        "lighting": "暖色轮廓光",
        "color_palette": ["#f59e0b", "#1c1917"],
        "origin": "filmed",
        "confidence": 0.9,
        "prompt": "close-up of a coffee cup, warm rim light",
        "negative_prompt": "text, watermark",
        "transition": "soft cut",
        "remake_notes": "keep the steam visible",
    }
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
        db.add(
            Job(
                id="reference-job",
                project_id="reference-project",
                status="done",
                step="done",
                progress=1.0,
                metrics={
                    "calls": 2,
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 500_000,
                },
            )
        )
        db.add(
            Shot(
                id=1,
                project_id="reference-project",
                index=1,
                start_s=0.0,
                end_s=4.0,
                origin="filmed",
                confidence=0.9,
                transcript="清晨的第一杯咖啡。",
                analysis=analysis,
            )
        )
        db.add(
            Shot(
                id=2,
                project_id="reference-project",
                index=2,
                start_s=4.0,
                end_s=8.0,
                origin="filmed",
                confidence=0.9,
                analysis={**analysis, "subject": "餐桌", "shot_type": "全景"},
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


def create_prompt(client: TestClient) -> str:
    response = client.post(
        "/api/prompt-projects",
        json={
            "title": "模板测试方案",
            "idea": "用参考片里的暖光特写，做一个新的咖啡产品短片",
            "duration_s": 8.0,
            "shot_count": 2,
            "reference_project_id": "reference-project",
            "reference_mode": "style",
        },
    )
    assert response.status_code == 201
    return response.json()["prompt_project_id"]


def test_template_save_list_and_apply(phase1_client):
    client, _, _ = phase1_client

    saved = client.post(
        "/api/projects/reference-project/shots/1/save-template",
        json={
            "name": "暖光咖啡特写",
            "description": "适合清晨产品广告",
            "category": "产品",
            "tags": ["咖啡", "暖光"],
        },
    )
    assert saved.status_code == 201
    template = saved.json()
    assert template["shot_type"] == "特写"
    assert template["lighting"] == "暖色轮廓光"
    assert template["source_shot_index"] == 1

    listed = client.get("/api/shot-templates", params={"search": "咖啡"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template["id"]]

    project_id = create_prompt(client)
    applied = client.post(
        f"/api/prompt-projects/{project_id}/apply-template",
        json={
            "template_id": template["id"],
            "fields": ["shot_type", "lighting", "prompt"],
        },
    )
    assert applied.status_code == 200
    payload = applied.json()
    assert payload["plan"]["shots"]
    assert {shot["shot_type"] for shot in payload["plan"]["shots"]} == {"特写"}
    assert {shot["lighting"] for shot in payload["plan"]["shots"]} == {"暖色轮廓光"}
    assert {shot["prompt"] for shot in payload["plan"]["shots"]} == {
        "close-up of a coffee cup, warm rim light"
    }

    versions = client.get(f"/api/prompt-projects/{project_id}/versions").json()
    assert any(item["source"] == "template_apply" for item in versions)


def test_template_placeholders_use_target_shot_context(phase1_client):
    client, _, _ = phase1_client
    template_prompt = (
        "{{shot_type}} of {{subject}} in {{scene}}, {{lighting}}; "
        "style {{global_style}}; keep {{missing_key}}"
    )
    saved = client.post(
        "/api/projects/reference-project/shots/1/save-template",
        json={
            "name": "上下文占位符模板",
            "category": "产品",
            "tags": ["占位符"],
            "prompt_template": template_prompt,
        },
    )
    assert saved.status_code == 201
    template = saved.json()
    assert template["has_placeholders"] is True
    assert set(template["placeholders"]) >= {
        "shot_type",
        "subject",
        "scene",
        "lighting",
        "global_style",
        "missing_key",
    }

    project_id = create_prompt(client)
    before = client.get(f"/api/prompt-projects/{project_id}").json()
    target = before["plan"]["shots"][0]
    untouched_prompt = before["plan"]["shots"][1]["prompt"]
    expected_prompt = (
        f"{target['shot_type']} of {target['subject']} in {target['scene']}, "
        f"{target['lighting']}; style {before['plan']['global_style']}; keep {{{{missing_key}}}}"
    )

    applied = client.post(
        f"/api/prompt-projects/{project_id}/apply-template",
        json={
            "template_id": template["id"],
            "shot_indices": [1],
            "fields": ["prompt"],
        },
    )

    assert applied.status_code == 200
    payload = applied.json()
    assert payload["plan"]["shots"][0]["prompt"] == expected_prompt
    assert payload["plan"]["shots"][1]["prompt"] == untouched_prompt
    assert any("未知占位符" in item and "missing_key" in item for item in payload["plan"]["warnings"])


def test_template_empty_placeholder_is_replaced_and_reported(phase1_client):
    client, _, _ = phase1_client
    project_id = create_prompt(client)
    edited = client.patch(
        f"/api/prompt-projects/{project_id}/shots/1",
        json={"action": ""},
    )
    assert edited.status_code == 200
    saved = client.post(
        "/api/projects/reference-project/shots/1/save-template",
        json={
            "name": "空值占位符模板",
            "category": "测试",
            "prompt_template": "{{subject}} performs {{action}} now",
        },
    )
    template = saved.json()

    applied = client.post(
        f"/api/prompt-projects/{project_id}/apply-template",
        json={
            "template_id": template["id"],
            "shot_indices": [1],
            "fields": ["prompt"],
        },
    )

    assert applied.status_code == 200
    payload = applied.json()
    assert payload["plan"]["shots"][0]["prompt"].endswith("performs  now")
    assert any("action" in item and "没有可用值" in item for item in payload["plan"]["warnings"])


def test_template_tag_filters_and_facets(phase1_client):
    client, _, _ = phase1_client
    templates = []
    for payload in [
        {
            "name": "暖光产品模板",
            "category": "产品",
            "tags": ["咖啡", "暖光"],
            "prompt_template": "UNIQUE PRODUCT {{subject}}",
        },
        {
            "name": "冷光人像模板",
            "category": "人像",
            "tags": ["人物", "冷光"],
            "prompt_template": "portrait {{subject}}",
        },
        {
            "name": "自然风景模板",
            "category": "风景",
            "tags": ["自然", "暖光"],
            "prompt_template": "landscape {{scene}}",
        },
    ]:
        response = client.post(
            "/api/projects/reference-project/shots/1/save-template",
            json=payload,
        )
        assert response.status_code == 201
        templates.append(response.json())

    product = next(item for item in templates if item["category"] == "产品")
    both_tags = client.get(
        "/api/shot-templates",
        params={"tags": ["咖啡", "暖光"]},
    )
    assert [item["id"] for item in both_tags.json()] == [product["id"]]

    comma_tags = client.get(
        "/api/shot-templates",
        params={"tags": "咖啡,暖光"},
    )
    assert [item["id"] for item in comma_tags.json()] == [product["id"]]
    assert client.get(
        "/api/shot-templates",
        params={"tags": ["咖啡", "冷光"]},
    ).json() == []
    assert [item["id"] for item in client.get(
        "/api/shot-templates", params={"category": "人像"}
    ).json()] == [next(item["id"] for item in templates if item["category"] == "人像")]
    assert [item["id"] for item in client.get(
        "/api/shot-templates", params={"search": "UNIQUE"}
    ).json()] == [product["id"]]

    facets = client.get("/api/shot-templates/facets")
    assert facets.status_code == 200
    facet_data = facets.json()
    assert facet_data["total"] == 3
    category_counts = {item["value"]: item["count"] for item in facet_data["categories"]}
    tag_counts = {item["value"]: item["count"] for item in facet_data["tags"]}
    assert category_counts["产品"] == 1
    assert tag_counts["暖光"] == 2
    assert tag_counts["冷光"] == 1


def test_cost_summary_uses_configured_prices(phase1_client):
    client, testing_session, _ = phase1_client

    reverse = client.get("/api/projects/reference-project/cost")
    assert reverse.status_code == 200
    payload = reverse.json()
    assert payload["cost"]["calls"] == 2
    assert payload["cost"]["total_tokens"] == 1_500_000
    assert payload["cost"]["priced"] is True
    assert payload["cost"]["estimated_cost"] == 2.0

    project_id = create_prompt(client)
    with testing_session() as db:
        project = db.get(PromptProject, project_id)
        project.metrics = {
            "calls": 1,
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        }
        db.commit()
    prompt_cost = client.get(f"/api/prompt-projects/{project_id}/cost")
    assert prompt_cost.status_code == 200
    assert prompt_cost.json()["cost"]["estimated_cost"] == 0.002

    unpriced = cost.estimate_usage(
        {"prompt_tokens": 100, "completion_tokens": 50},
        Settings(llm_input_price_per_million=0, llm_output_price_per_million=0),
    )
    assert unpriced["priced"] is False
    assert unpriced["estimated_cost"] is None


def test_cost_estimate_uses_duration_and_manual_shots(phase1_client):
    client, _, _ = phase1_client

    response = client.post(
        "/api/projects/estimate-cost",
        json={"video_duration": 60},
    )
    assert response.status_code == 200
    estimate = response.json()
    assert estimate["video_duration"] == 60.0
    assert estimate["estimated_shots"] == 18
    assert estimate["shot_count_source"] == "heuristic"
    assert estimate["cost"]["calls"] == 18
    assert estimate["cost"]["prompt_tokens"] == 27_000
    assert estimate["cost"]["completion_tokens"] == 8_100
    assert estimate["cost"]["vision_cost"] == 0.0432
    assert estimate["cost"]["text_cost"] == 0.0
    assert estimate["cost"]["total_cost"] == 0.0432
    assert estimate["billable"] is False
    assert any("MAX_SHOTS" in item for item in estimate["suggestions"])
    assert any("MOCK" in item.upper() for item in estimate["suggestions"])
    assert any("视频生成费用" in item for item in estimate["suggestions"])

    manual = client.post(
        "/api/projects/estimate-cost",
        json={"video_duration": 60, "estimated_shots": 12},
    )
    assert manual.status_code == 200
    payload = manual.json()
    assert payload["estimated_shots"] == 12
    assert payload["shot_count_source"] == "manual"
    assert payload["cost"]["prompt_tokens"] == 18_000
    assert not any("MAX_SHOTS" in item for item in payload["suggestions"])


def test_cost_estimate_caps_shots_and_handles_unpriced_settings(phase1_client):
    client, _, settings = phase1_client

    response = client.post(
        "/api/projects/estimate-cost",
        json={"video_duration": 120, "estimated_shots": 50},
    )
    assert response.status_code == 200
    estimate = response.json()
    assert estimate["estimated_shots"] == settings.max_shots
    assert estimate["requested_shots"] == 50
    assert any("MAX_SHOTS" in item for item in estimate["suggestions"])

    unpriced = cost.estimate_project_cost(
        30,
        None,
        Settings(
            llm_input_price_per_million=0,
            llm_output_price_per_million=0,
        ),
    )
    assert unpriced["cost"]["estimated_cost"] is None
    assert unpriced["cost"]["vision_cost"] is None
    assert any("未配置模型单价" in item for item in unpriced["suggestions"])


def test_quality_dashboard_aggregates_edits_and_trend(phase1_client):
    client, _, _ = phase1_client

    baseline = client.get("/api/insights/quality", params={"days": 30})
    assert baseline.status_code == 200
    assert baseline.json()["summary"]["origin_accuracy"] is None

    origin_edit = client.patch(
        "/api/projects/reference-project/shots/1",
        json={"origin": "ai_generated"},
    )
    assert origin_edit.status_code == 200
    lighting_edit = client.patch(
        "/api/projects/reference-project/shots/2",
        json={"lighting": "冷色环境光"},
    )
    assert lighting_edit.status_code == 200

    response = client.get("/api/insights/quality", params={"days": 30})
    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]

    assert summary["projects"] == 1
    assert summary["shots"] == 2
    assert summary["edit_events"] == 2
    assert summary["edited_shots"] == 2
    assert summary["origin_corrections"] == 1
    assert summary["origin_accuracy"] == 0.5
    assert summary["correction_rate"] == 1.0
    assert summary["analysis_runs"] == 1
    assert summary["total_tokens"] == 1_500_000
    assert summary["total_calls"] == 2
    assert summary["average_processing_seconds"] is not None

    fields = {item["field"]: item for item in payload["fields"]}
    assert fields["origin"]["count"] == 1
    assert fields["origin"]["affected_shots"] == 1
    assert fields["lighting"]["count"] == 1
    assert fields["lighting"]["rate"] == 0.5

    assert len(payload["trend"]) == 30
    assert sum(item["edit_events"] for item in payload["trend"]) == 2
    assert sum(item["field_corrections"] for item in payload["trend"]) == 2
    assert sum(item["origin_corrections"] for item in payload["trend"]) == 1

    assert payload["projects"][0]["id"] == "reference-project"
    assert payload["projects"][0]["edit_events"] == 2
    assert payload["projects"][0]["edited_shots"] == 2
    assert any("来源判定修正" in item for item in payload["suggestions"])
    assert any("样本量较小" in item for item in payload["suggestions"])

    weekly = client.get("/api/insights/quality", params={"days": 7})
    assert weekly.status_code == 200
    assert len(weekly.json()["trend"]) == 7
    assert client.get("/api/insights/quality", params={"days": 3}).status_code == 422


def test_shot_edit_records_audit_event(phase1_client):
    client, _, _ = phase1_client

    updated = client.patch(
        "/api/projects/reference-project/shots/1",
        json={"subject": "手冲咖啡壶", "transcript": "新的旁白"},
    )
    assert updated.status_code == 200

    events = client.get("/api/projects/reference-project/edit-events")
    assert events.status_code == 200
    payload = events.json()
    assert len(payload) == 1
    changes = payload[0]["changes"]
    assert changes["subject"] == {"before": "咖啡杯", "after": "手冲咖啡壶"}
    assert changes["transcript"] == {
        "before": "清晨的第一杯咖啡。",
        "after": "新的旁白",
    }


def test_phase1_frontend_hooks_are_present():
    root = Path(__file__).resolve().parent.parent
    html = (root / "app" / "templates" / "index.html").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "style.css").read_text(encoding="utf-8")
    app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    prompt_js = (root / "app" / "static" / "prompt.js").read_text(encoding="utf-8")
    shared_js = (root / "app" / "static" / "shared.js").read_text(encoding="utf-8")

    assert 'id="template-dialog"' in html
    assert html.count("data-close-template") == 2
    assert "data-save-template" in app_js
    assert 'querySelectorAll("[data-close-template]")' in app_js
    assert "一键生成复刻方案" in app_js
    assert "SHOT TEMPLATE LIBRARY" in prompt_js
    assert "data-apply-template" in prompt_js
    assert 'id="template-prompt-template"' in html
    assert "data-insert-template-placeholder" in html
    assert "template-category-filter" in prompt_js
    assert "template-tag-filters" in prompt_js
    assert "/api/shot-templates/facets" in prompt_js
    assert 'id="cost-estimate"' in html
    assert "estimate-cost" in app_js
    assert "costEstimateMarkup" in app_js
    assert 'id="quality-view"' in html
    assert "data-quality-refresh" in html
    assert "loadQualityDashboard" in app_js
    assert "quality-trend-chart" in app_js
    assert "#quality" in prompt_js
    assert "usageMarkup" in shared_js
    assert ".usage-strip" in css
    assert ".cost-estimate" in css
    assert ".quality-kpis" in css
    assert ".template-dialog" in css
    assert ".template-placeholder-panel" in css
    assert ".template-tag-chip.is-selected" in css
    assert "timelineMarkup" in app_js
    assert "data-timeline-boundary" in app_js
    assert "timeline_min_shot_seconds" in app_js
    assert "/shots/merge" in app_js
    assert ".shot-timeline" in css
    assert ".timeline-handle" in css
