import logging
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..db import SessionLocal
from ..models import DeliveryReview, PromptProject
from ..schemas import PromptPlan
from . import media

logger = logging.getLogger(__name__)


def _update_review(
    db,
    review: DeliveryReview,
    *,
    status: str | None = None,
    step: str | None = None,
    progress: float | None = None,
    error: str | None = None,
) -> None:
    if status is not None:
        review.status = status
    if step is not None:
        review.step = step
    if progress is not None:
        review.progress = max(0.0, min(1.0, progress))
    if error is not None:
        review.error = error
    review.updated_at = datetime.now(timezone.utc)
    db.commit()


def run_delivery_review(review_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        review = db.get(DeliveryReview, review_id)
        if review is None:
            return
        project = db.get(PromptProject, review.prompt_project_id)
        if project is None:
            review.status = "failed"
            review.error = "提示词方案不存在"
            db.commit()
            return
        try:
            plan = PromptPlan.model_validate(project.plan_json or {})
            _update_review(db, review, status="running", step="probing", progress=0.08)
            result = evaluate_delivery(Path(review.source_path), plan, settings)
            review.result_json = result
            _update_review(
                db,
                review,
                status="done",
                step="done",
                progress=1.0,
                error="",
            )
        except Exception as exc:
            logger.exception("delivery review failed: %s", review_id)
            review.status = "failed"
            review.step = "failed"
            review.error = str(exc)[:2000]
            review.updated_at = datetime.now(timezone.utc)
            db.commit()


def evaluate_delivery(path: Path, plan: PromptPlan, settings) -> dict:
    if not path.exists():
        raise FileNotFoundError("成片文件不存在")
    meta = media.probe(path, settings)
    segments = media.detect_shots(path, meta, settings)
    ffmpeg = media.resolve_ffmpeg(settings.ffmpeg_bin)
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法抽帧回测")

    actual = []
    for start, end in segments:
        midpoint = start + max(0.0, end - start) / 2
        actual.append(
            {
                "start_s": round(start, 3),
                "end_s": round(end, 3),
                "duration": round(max(0.0, end - start), 3),
                "color": _average_color(ffmpeg, path, midpoint),
            }
        )

    aspect_score = _aspect_score(plan.aspect_ratio, meta.width, meta.height)
    expected = plan.shots
    rows = []
    duration_scores = []
    for index, expected_shot in enumerate(expected):
        actual_shot = actual[index] if index < len(actual) else None
        if actual_shot is None:
            rows.append(
                {
                    "index": expected_shot.index,
                    "expected_duration": expected_shot.duration,
                    "actual_duration": None,
                    "duration_score": 0.0,
                    "color": "",
                    "color_score": 0.0,
                    "execution_score": 0.0,
                }
            )
            duration_scores.append(0.0)
            continue
        duration_score = 1.0 - min(
            1.0,
            abs(actual_shot["duration"] - expected_shot.duration)
            / max(expected_shot.duration, 0.1),
        )
        color_score = _nearest_palette_score(
            actual_shot["color"], expected_shot.color_palette
        )
        execution_score = round(
            0.7 * duration_score + 0.2 * color_score + 0.1 * aspect_score, 3
        )
        duration_scores.append(duration_score)
        rows.append(
            {
                "index": expected_shot.index,
                "expected_duration": expected_shot.duration,
                "actual_duration": actual_shot["duration"],
                "duration_score": round(duration_score, 3),
                "color": actual_shot["color"],
                "color_score": round(color_score, 3),
                "execution_score": execution_score,
            }
        )

    coverage = min(1.0, len(actual) / len(expected)) if expected else 0.0
    execution_score = round(
        (sum(duration_scores) / len(duration_scores) if duration_scores else 0.0)
        * 0.8
        + coverage * 0.15
        + aspect_score * 0.05,
        3,
    )
    expected_palette = [
        color for shot in expected for color in (shot.color_palette or [])
    ]
    actual_palette = [shot["color"] for shot in actual if shot["color"]]
    style_score = _palette_similarity(expected_palette, actual_palette)
    warnings = []
    if len(actual) != len(expected):
        warnings.append(
            f"成片识别到 {len(actual)} 个镜头，方案规划 {len(expected)} 个；已按顺序对齐。"
        )
    if not actual_palette:
        warnings.append("未能从成片抽帧读取颜色，风格相似度仅供参考。")
    warnings.append("回测基于镜头时长、画幅和抽帧主色，不等同于视觉语义审核。")
    overall = round(
        execution_score * 0.55
        + (style_score if style_score is not None else execution_score) * 0.45,
        3,
    )
    return {
        "summary": {
            "execution_score": execution_score,
            "style_score": style_score,
            "overall_score": overall,
            "expected_shots": len(expected),
            "actual_shots": len(actual),
            "expected_duration": round(plan.duration_s, 3),
            "actual_duration": round(meta.duration, 3),
            "width": meta.width,
            "height": meta.height,
            "aspect_score": round(aspect_score, 3),
        },
        "style": {
            "expected_palette": list(dict.fromkeys(expected_palette))[:8],
            "actual_palette": list(dict.fromkeys(actual_palette))[:8],
        },
        "shots": rows,
        "warnings": warnings,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def _aspect_score(ratio: str, width: int, height: int) -> float:
    if not width or not height:
        return 0.0
    try:
        left, right = ratio.split(":", 1)
        target = float(left) / float(right)
    except (ValueError, ZeroDivisionError):
        return 0.0
    actual = width / height
    return max(0.0, 1.0 - abs(actual - target) / max(target, 0.1))


def _average_color(ffmpeg: str, video: Path, timestamp: float) -> str:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "scale=1:1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=60)
        data = completed.stdout[:3]
        if completed.returncode != 0 or len(data) < 3:
            return ""
        return "#{:02x}{:02x}{:02x}".format(data[0], data[1], data[2])
    except Exception as exc:
        logger.warning("average color failed: %s", exc)
        return ""


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def _nearest_palette_score(color: str, palette: list[str]) -> float:
    actual = _hex_rgb(color)
    if actual is None:
        return 0.0
    candidates = [rgb for item in palette if (rgb := _hex_rgb(item))]
    if not candidates:
        return 0.0
    closest = min(
        math.sqrt(sum((left - right) ** 2 for left, right in zip(actual, candidate)))
        for candidate in candidates
    )
    return max(0.0, 1.0 - closest / math.sqrt(3 * 255**2))


def _palette_similarity(expected: list[str], actual: list[str]) -> float | None:
    colors = [color for color in expected if _hex_rgb(color)]
    if not colors or not actual:
        return None
    scores = [_nearest_palette_score(color, actual) for color in colors]
    return round(sum(scores) / len(scores), 3)
