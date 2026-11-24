from app.schemas import ShotAnalysis
from app.services.fusion import attach_transcript, build_recipe
from app.services.media import VideoMeta


def test_attach_transcript_uses_overlap():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "第一句"},
        {"start": 2.0, "end": 4.0, "text": "第二句"},
        {"start": 8.0, "end": 9.0, "text": "无关"},
    ]
    assert attach_transcript(segments, 1.0, 3.0) == "第一句 第二句"
    assert attach_transcript(segments, 5.0, 7.0) == ""


def test_build_recipe_computes_pacing():
    analysis = ShotAnalysis(
        shot_type="中景",
        camera_movement="固定",
        subject="人物",
        scene="街道",
        visual_style="写实",
        lighting="自然光",
        origin="filmed",
        confidence=0.9,
        prompt="medium shot of a person on the street",
    )
    rows = [
        {"index": i + 1, "start_s": float(i), "end_s": float(i + 1), "analysis": analysis, "transcript": ""}
        for i in range(10)
    ]
    recipe = build_recipe("测试", "a.mp4", VideoMeta(duration=10.0, width=1280, height=720, fps=30), rows)
    assert recipe.cut_count == 9
    assert recipe.cuts_per_minute == 54.0
    assert recipe.pacing == "fast"
    assert recipe.origin_counts == {"filmed": 10}