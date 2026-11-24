import csv
import io
import json
import zipfile
from pathlib import Path

from ..config import Settings
from ..models import Project, PromptProject, PromptVersion, Shot
from ..schemas import PromptPlan, Recipe
from . import prompt_export
from . import recipe as recipe_service


def _clock_srt(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_shots_csv(plan: PromptPlan) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "index",
            "start_s",
            "end_s",
            "duration",
            "shot_type",
            "camera_movement",
            "subject",
            "action",
            "scene",
            "lighting",
            "transition",
            "prompt",
            "negative_prompt",
            "source_shot_index",
            "locked_fields",
        ]
    )
    for shot in plan.shots:
        writer.writerow(
            [
                shot.index,
                shot.start_s,
                shot.end_s,
                shot.duration,
                shot.shot_type,
                shot.camera_movement,
                shot.subject,
                shot.action,
                shot.scene,
                shot.lighting,
                shot.transition,
                shot.prompt,
                shot.negative_prompt,
                shot.source_shot_index or "",
                ",".join(shot.locked_fields),
            ]
        )
    return output.getvalue()


def render_shots_srt(plan: PromptPlan) -> str:
    blocks = []
    for position, shot in enumerate(plan.shots, start=1):
        text = " / ".join(
            value for value in [shot.subject, shot.action, shot.scene] if value
        ) or shot.prompt
        blocks.append(
            f"{position}\n{_clock_srt(shot.start_s)} --> {_clock_srt(shot.end_s)}\n{text}\n"
        )
    return "\n".join(blocks)


def _keyframe_path(settings: Settings, shot: Shot) -> Path | None:
    if not shot.keyframe_path:
        return None
    path = Path(shot.keyframe_path)
    if not path.is_absolute():
        path = settings.data_dir / path
    return path if path.is_file() else None


def build_prompt_zip(
    project: PromptProject,
    plan: PromptPlan,
    versions: list[PromptVersion],
    settings: Settings,
    source_project: Project | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("prompt-plan.md", prompt_export.render_prompt_markdown(plan))
        archive.writestr("prompt-plan.json", prompt_export.render_prompt_json(plan))
        archive.writestr("shots.csv", render_shots_csv(plan))
        archive.writestr("shots.srt", render_shots_srt(plan))
        archive.writestr(
            "entity-bible.json",
            json.dumps(project.entity_bible_json or {}, ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "versions.json",
            json.dumps(
                [
                    {
                        "version": version.version,
                        "source": version.source,
                        "created_at": version.created_at.isoformat()
                        if version.created_at
                        else None,
                        "shot_count": len((version.plan_json or {}).get("shots") or []),
                    }
                    for version in versions
                ],
                ensure_ascii=False,
                indent=2,
            ),
        )

        reference = project.reference_snapshot_json or {}
        if reference.get("recipe"):
            recipe = Recipe.model_validate(reference["recipe"])
            archive.writestr("reference/video.md", recipe_service.render_markdown(recipe))
            archive.writestr("reference/video.json", recipe_service.render_json(recipe))

        if source_project is not None:
            by_index = {shot.index: shot for shot in source_project.shots}
            for generated in plan.shots:
                source = by_index.get(generated.source_shot_index or 0)
                path = _keyframe_path(settings, source) if source else None
                if path:
                    archive.write(
                        path,
                        f"keyframes/ref-shot-{source.index:02d}{path.suffix or '.jpg'}",
                    )

        manifest = (
            f"# {plan.title or project.title}\n\n"
            f"- 目标模型：{plan.target_model}\n"
            f"- 时长：{plan.duration_s:.1f}s\n"
            f"- 画幅：{plan.aspect_ratio}\n"
            f"- 镜头数：{len(plan.shots)}\n"
            f"- 版本：{versions[-1].version if versions else 0}\n\n"
            "## 文件\n\n"
            "- prompt-plan.md / prompt-plan.json：完整分镜与 Prompt\n"
            "- shots.csv：可导入表格的镜头表\n"
            "- shots.srt：按镜头时间轴生成的字幕骨架\n"
            "- entity-bible.json：角色、产品、服装与场景一致性设定\n"
            "- versions.json：版本历史摘要\n"
            "- reference/：参考项目 Recipe（如有）\n"
            "- keyframes/：参考镜头关键帧（如有）\n"
        )
        archive.writestr("README.md", manifest)
    return buffer.getvalue()
