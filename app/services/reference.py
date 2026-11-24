from collections import Counter
from pathlib import Path

from ..config import Settings, get_settings
from ..models import Project
from ..schemas import Recipe, ReferenceContext, ReferenceMode, ShotAnalysis
from . import recipe as recipe_service
from .fusion import build_recipe
from .media import VideoMeta
from .pipeline import project_dir

_ASPECTS = [
    (16, 9, "16:9"),
    (9, 16, "9:16"),
    (1, 1, "1:1"),
    (4, 3, "4:3"),
    (21, 9, "21:9"),
]


def aspect_ratio_for(width: int, height: int) -> str:
    if not width or not height:
        return "16:9"
    target = width / height
    return min(_ASPECTS, key=lambda item: abs(item[0] / item[1] - target))[2]


def build_reference_context(
    project: Project,
    mode: ReferenceMode = "style",
) -> ReferenceContext:
    rows = []
    for shot in project.shots:
        analysis = ShotAnalysis.model_validate(shot.analysis or {})
        rows.append(
            {
                "index": shot.index,
                "start_s": shot.start_s,
                "end_s": shot.end_s,
                "analysis": analysis,
                "transcript": shot.transcript,
            }
        )
    meta = VideoMeta(
        duration=project.duration,
        width=project.width,
        height=project.height,
        fps=project.fps,
    )
    recipe = build_recipe(
        title=project.title,
        source_filename=Path(project.source_path).name,
        meta=meta,
        shot_rows=rows,
    )
    return ReferenceContext(project_id=project.id, mode=mode, recipe=recipe)


def compact_reference(context: ReferenceContext) -> dict:
    recipe = context.recipe
    shots = recipe.shots
    shot_types = Counter(shot.shot_type for shot in shots)
    movements = Counter(shot.camera_movement for shot in shots)
    lighting = [shot.lighting for shot in shots if shot.lighting]
    palette = []
    for shot in shots:
        for color in shot.color_palette:
            if color not in palette:
                palette.append(color)

    style = {
        "title": recipe.title,
        "duration_s": recipe.duration,
        "aspect_ratio": aspect_ratio_for(recipe.width, recipe.height),
        "pacing": recipe.pacing,
        "avg_shot_seconds": recipe.avg_shot_seconds,
        "summary": recipe.summary,
        "palette": palette[:8],
        "shot_types": dict(shot_types),
        "camera_movements": dict(movements),
        "lighting": list(dict.fromkeys(lighting))[:8],
        "visual_style": next((shot.visual_style for shot in shots if shot.visual_style), ""),
    }
    payload = {"mode": context.mode, "style": style}
    if context.mode in {"structure", "full"}:
        payload["shots"] = [
            {
                "index": shot.index,
                "duration": shot.duration,
                "shot_type": shot.shot_type,
                "camera_movement": shot.camera_movement,
                "lighting": shot.lighting,
                "color_palette": shot.color_palette,
                "scene": shot.scene if context.mode == "full" else "",
                "subject": shot.subject if context.mode == "full" else "",
                "prompt": shot.prompt if context.mode == "full" else "",
            }
            for shot in shots[:12]
        ]
    return payload


def rebuild_project_recipe(
    project: Project,
    settings: Settings | None = None,
) -> Recipe:
    """Rebuild and persist the recipe after a shot analysis edit."""
    settings = settings or get_settings()
    recipe = build_reference_context(project, "style").recipe
    output_dir = project_dir(project.id, settings) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "video.md").write_text(
        recipe_service.render_markdown(recipe), encoding="utf-8"
    )
    (output_dir / "video.json").write_text(
        recipe_service.render_json(recipe), encoding="utf-8"
    )
    return recipe
