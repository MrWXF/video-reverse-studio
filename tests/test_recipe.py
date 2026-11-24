import json
from datetime import datetime, timezone

from app.schemas import Recipe, RecipeShot
from app.services.recipe import render_json, render_markdown


def make_recipe() -> Recipe:
    return Recipe(
        title="测试片",
        source_filename="source.mp4",
        duration=6.0,
        width=640,
        height=360,
        fps=25.0,
        shots=[
            RecipeShot(
                index=1,
                start_s=0.0,
                end_s=3.0,
                duration=3.0,
                shot_type="特写",
                camera_movement="缓慢推镜",
                subject="咖啡豆",
                scene="棚拍",
                visual_style="广告质感",
                lighting="侧逆光",
                color_palette=["#1c1917", "#f59e0b"],
                origin="filmed",
                confidence=0.82,
                evidence=["自然噪点", "真实景深"],
                prompt="extreme close-up of coffee beans falling in slow motion, macro lens",
                remake_notes="注意高光不要过曝",
                transcript="新鲜烘焙",
            ),
            RecipeShot(
                index=2,
                start_s=3.0,
                end_s=6.0,
                duration=3.0,
                shot_type="全景",
                camera_movement="横移",
                subject="咖啡馆",
                scene="室内",
                visual_style="写实电影感",
                lighting="自然柔光",
                color_palette=["#0f172a"],
                origin="ai_generated",
                confidence=0.61,
                evidence=["边缘融合"],
                prompt="wide shot of a cozy cafe, slow lateral dolly",
                remake_notes="",
                transcript="",
            ),
        ],
        cut_count=1,
        cuts_per_minute=10.0,
        avg_shot_seconds=3.0,
        pacing="slow",
        origin_counts={"filmed": 1, "ai_generated": 1},
        summary="测试摘要",
        generated_at=datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc),
    )


def test_render_markdown_contains_core_sections():
    text = render_markdown(make_recipe())
    assert text.startswith("---")
    assert "# 测试片" in text
    assert "## 镜头表" in text
    assert "Shot 01" in text
    assert "实拍" in text
    assert "AI 生成" in text
    assert "extreme close-up" in text


def test_render_json_roundtrip():
    payload = json.loads(render_json(make_recipe()))
    assert payload["title"] == "测试片"
    assert payload["shots"][0]["origin"] == "filmed"
    assert payload["generated_at"].startswith("2026-11-21")