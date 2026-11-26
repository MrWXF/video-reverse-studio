"""Deterministic mock analysis used when model providers are disabled or unavailable."""

import hashlib
import time

from ..prompts import load_catalog
from ..schemas import ShotAnalysis


class MockScenarioError(RuntimeError):
    """Raised when a configured mock failure scenario is requested."""


def _pick(values: list, seed: int):
    """Select a deterministic list item from a seed."""
    return values[seed % len(values)]


def mock_analysis(
    index: int,
    start_s: float,
    end_s: float,
    transcript: str = "",
    *,
    scenario: str = "success",
    fail_shot: int = 0,
    catalog_path: str = "",
) -> ShotAnalysis:
    """Build a deterministic mock analysis from shot timing and transcript.

    ``MOCK_SCENARIO=fail`` fails every call. ``MOCK_SCENARIO=fail_shot`` fails
    when ``index`` reaches ``MOCK_FAIL_SHOT``. ``slow`` adds a short delay so
    cancellation and SSE behavior can be exercised without a real provider.
    """
    scenario = (scenario or "success").lower().strip()
    if scenario == "fail" or (scenario == "fail_shot" and fail_shot and index >= fail_shot):
        raise MockScenarioError(f"Mock 已按配置模拟镜头 {index} 失败")
    if scenario == "slow":
        time.sleep(0.05)

    catalog = load_catalog(catalog_path)
    transcript = (transcript or "").strip()
    seed_text = f"{index}:{start_s:.2f}:{end_s:.2f}:{transcript}"
    seed = int(hashlib.sha1(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    shot_type = _pick(catalog["shot_types"], seed)
    move = _pick(catalog["camera_moves"], seed // 7)
    palette = _pick(catalog["palettes"], seed // 11)
    origin = _pick(catalog["origins"], seed // 13)
    confidence = round(0.55 + (seed % 35) / 100, 2)
    subject = _pick(catalog["subjects"], seed // 17)
    scene = _pick(catalog["scenes"], seed // 19)
    style = _pick(catalog["styles"], seed // 23)
    evidence = [
        "Mock 模式：未调用视觉模型",
        f"镜头时长 {max(0.0, end_s - start_s):.1f}s，运动强度由模拟规则生成",
    ]
    if transcript:
        evidence.append(f"已纳入台词特征：{transcript[:100]}")
    prompt = (
        f"{style} {shot_type} of {subject} in {scene}, {move}, "
        f"cinematic lighting, shallow depth of field, 35mm lens, "
        f"color palette {', '.join(palette)}, 24fps"
    )
    if transcript:
        prompt += f", dialogue context: {transcript[:120]}"
    return ShotAnalysis(
        shot_type=shot_type,
        camera_movement=move,
        subject=subject,
        scene=scene,
        visual_style=style,
        lighting="自然柔光" if origin == "filmed" else "程序化布光",
        color_palette=palette,
        origin=origin,
        confidence=confidence,
        evidence=evidence,
        prompt=prompt,
        remake_notes=(
            "Mock 结果仅用于流程演示，配置视觉模型后重新分析可获得真实判断。"
        ),
    )
