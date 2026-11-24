import json

from app.schemas import PromptBrief
from app.services.prompt_export import render_prompt_json, render_prompt_markdown
from app.services.prompt_generation import mock_prompt_plan, normalize_prompt_plan


def build_plan():
    brief = PromptBrief(
        title="咖啡广告",
        idea="清晨厨房咖啡广告",
        duration_s=9.0,
        shot_count=3,
        target_model="veo",
        negative_prompt="watermark, text",
    )
    return normalize_prompt_plan(mock_prompt_plan(brief), brief)


def test_render_prompt_markdown_contains_storyboard_and_prompts():
    plan = build_plan()

    markdown = render_prompt_markdown(plan)

    assert "# 咖啡广告" in markdown
    assert "## 镜头表" in markdown
    assert "## 逐镜提示词" in markdown
    assert "**Prompt**" in markdown
    assert "**Negative Prompt**" in markdown
    assert "Shot 01" in markdown
    assert plan.shots[0].prompt in markdown


def test_render_prompt_json_round_trips_plan():
    plan = build_plan()

    data = json.loads(render_prompt_json(plan))

    assert data["title"] == "咖啡广告"
    assert data["target_model"] == "veo"
    assert len(data["shots"]) == 3
    assert data["shots"][0]["prompt"] == plan.shots[0].prompt
    assert data["generated_at"]
