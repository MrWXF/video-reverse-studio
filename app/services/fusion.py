from collections import Counter
from datetime import datetime, timezone

from ..schemas import Recipe, RecipeShot, ShotAnalysis
from .media import VideoMeta


def attach_transcript(segments: list[dict], start: float, end: float) -> str:
    if not segments:
        return ""
    if end <= start:
        end = start + 0.01
    texts = [
        str(segment.get("text", "")).strip()
        for segment in segments
        if float(segment.get("end", 0.0)) > start
        and float(segment.get("start", 0.0)) < end
    ]
    return " ".join(text for text in texts if text)


def _pacing(cuts_per_minute: float) -> str:
    if cuts_per_minute >= 30:
        return "fast"
    if cuts_per_minute >= 12:
        return "medium"
    return "slow"


def _summary(shots: list[RecipeShot], duration: float, pacing: str) -> str:
    if not shots:
        return "未识别到有效镜头。"
    origins = Counter(shot.origin for shot in shots)
    types = Counter(shot.shot_type for shot in shots)
    main_type, main_count = types.most_common(1)[0]
    origin_text = "、".join(f"{key} {value} 个" for key, value in origins.most_common())
    pace_text = {"fast": "快节奏", "medium": "中速", "slow": "慢节奏"}[pacing]
    return (
        f"全片约 {duration:.1f} 秒，共 {len(shots)} 个镜头，{pace_text}剪辑；"
        f"以{main_type}为主（{main_count} 个）。来源分布：{origin_text}。"
        "建议先按镜头表复刻景别与运镜，再用逐镜提示词匹配光线和色调。"
    )


def build_recipe(
    title: str,
    source_filename: str,
    meta: VideoMeta,
    shot_rows: list[dict],
    generated_at: datetime | None = None,
) -> Recipe:
    shots: list[RecipeShot] = []
    for row in shot_rows:
        analysis: ShotAnalysis = row["analysis"]
        start = float(row["start_s"])
        end = float(row["end_s"])
        shots.append(
            RecipeShot(
                index=int(row["index"]),
                start_s=start,
                end_s=end,
                duration=max(0.0, end - start),
                shot_type=analysis.shot_type,
                camera_movement=analysis.camera_movement,
                subject=analysis.subject,
                scene=analysis.scene,
                visual_style=analysis.visual_style,
                lighting=analysis.lighting,
                color_palette=analysis.color_palette,
                origin=analysis.origin,
                confidence=analysis.confidence,
                evidence=analysis.evidence,
                prompt=analysis.prompt,
                remake_notes=analysis.remake_notes,
                transcript=str(row.get("transcript", "")),
            )
        )

    duration = meta.duration or (shots[-1].end_s if shots else 0.0)
    cut_count = max(0, len(shots) - 1)
    cuts_per_minute = (cut_count / duration * 60.0) if duration > 0 else 0.0
    pacing = _pacing(cuts_per_minute)
    average = (duration / len(shots)) if shots else 0.0
    origin_counts = dict(Counter(shot.origin for shot in shots))

    return Recipe(
        title=title,
        source_filename=source_filename,
        duration=duration,
        width=meta.width,
        height=meta.height,
        fps=meta.fps,
        shots=shots,
        cut_count=cut_count,
        cuts_per_minute=round(cuts_per_minute, 2),
        avg_shot_seconds=round(average, 2),
        pacing=pacing,
        origin_counts=origin_counts,
        summary=_summary(shots, duration, pacing),
        generated_at=generated_at or datetime.now(timezone.utc),
    )