import hashlib

from ..schemas import ShotAnalysis

_SHOT_TYPES = ["远景", "全景", "中景", "近景", "特写"]
_MOVES = ["固定", "缓慢推镜", "横移", "手持跟随", "环绕"]
_PALETTES = [
    ["#0f172a", "#38bdf8", "#e2e8f0"],
    ["#1c1917", "#f59e0b", "#fef3c7"],
    ["#052e16", "#22c55e", "#dcfce7"],
    ["#3b0764", "#a855f7", "#f3e8ff"],
]
_SUBJECTS = ["人物", "产品", "街景", "手部特写", "自然景观"]
_SCENES = ["室内", "城市街道", "自然户外", "纯色背景棚拍", "夜景"]
_STYLES = ["写实电影感", "广告质感", "纪录片", "赛博朋克", "极简"]
_ORIGINS = ["filmed", "ai_generated", "code_generated"]


def mock_analysis(index: int, start_s: float, end_s: float, transcript: str = "") -> ShotAnalysis:
    seed_text = f"{index}:{start_s:.2f}:{end_s:.2f}"
    seed = int(hashlib.sha1(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    shot_type = _SHOT_TYPES[seed % len(_SHOT_TYPES)]
    move = _MOVES[(seed // 7) % len(_MOVES)]
    palette = _PALETTES[(seed // 11) % len(_PALETTES)]
    origin = _ORIGINS[(seed // 13) % len(_ORIGINS)]
    confidence = round(0.55 + (seed % 35) / 100, 2)
    subject = _SUBJECTS[(seed // 17) % len(_SUBJECTS)]
    scene = _SCENES[(seed // 19) % len(_SCENES)]
    style = _STYLES[(seed // 23) % len(_STYLES)]
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
        evidence=[
            "Mock 模式：未调用视觉模型",
            f"镜头时长 {max(0.0, end_s - start_s):.1f}s，运动强度由模拟规则生成",
        ],
        prompt=(
            f"{style} {shot_type} of {subject} in {scene}, {move}, "
            f"cinematic lighting, shallow depth of field, 35mm lens, "
            f"color palette {', '.join(palette)}, 24fps"
        ),
        remake_notes="Mock 结果仅用于流程演示，配置视觉模型后重新分析可获得真实判断。",
    )