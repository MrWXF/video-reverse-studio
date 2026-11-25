"""Reusable shot templates and template application to prompt plans."""

from __future__ import annotations

from ..models import Shot, ShotTemplate
from ..schemas import PromptPlan, ShotTemplateApply, ShotTemplateSave

STYLE_FIELDS = (
    "shot_type",
    "camera_movement",
    "lighting",
    "color_palette",
    "transition",
)
PROMPT_FIELDS = ("prompt", "negative_prompt", "remake_notes")
ALLOWED_FIELDS = STYLE_FIELDS + PROMPT_FIELDS


def _clean_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        tag = str(value or "").strip()[:50]
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:20]


def template_from_shot(
    shot: Shot,
    payload: ShotTemplateSave,
) -> ShotTemplate:
    analysis = shot.analysis or {}
    return ShotTemplate(
        name=payload.name,
        description=payload.description,
        category=payload.category or "自定义",
        tags=_clean_tags(payload.tags),
        shot_type=str(analysis.get("shot_type") or "")[:80],
        camera_movement=str(analysis.get("camera_movement") or "")[:100],
        lighting=str(analysis.get("lighting") or "")[:200],
        visual_style=str(analysis.get("visual_style") or "")[:300],
        color_palette=[
            str(color)[:50]
            for color in (analysis.get("color_palette") or [])
            if str(color).strip()
        ],
        prompt_template=str(analysis.get("prompt") or ""),
        negative_prompt=str(analysis.get("negative_prompt") or ""),
        transition=str(analysis.get("transition") or "")[:100],
        remake_notes=str(analysis.get("remake_notes") or ""),
        source_project_id=shot.project_id,
        source_shot_index=shot.index,
    )


def apply_template(
    plan: PromptPlan,
    template: ShotTemplate,
    payload: ShotTemplateApply,
) -> list[str]:
    """Apply only the requested fields; return user-visible warnings."""
    requested = [field for field in payload.fields if field in ALLOWED_FIELDS]
    selected = set(payload.shot_indices)
    target_shots = [
        shot for shot in plan.shots if not selected or shot.index in selected
    ]
    available_indices = {shot.index for shot in plan.shots}
    warnings: list[str] = []
    if selected:
        missing = sorted(selected - available_indices)
        if missing:
            warnings.append(f"模板未应用到不存在的镜头：{', '.join(map(str, missing))}")
    if not target_shots:
        warnings.append("没有找到可应用模板的镜头")
        return warnings

    applied = 0
    for shot in target_shots:
        for field in requested:
            value = getattr(
                template,
                "prompt_template" if field == "prompt" else field,
                None,
            )
            if value in (None, "", []):
                continue
            setattr(shot, field, value)
            applied += 1
    if not applied:
        warnings.append("模板没有可应用的内容")
    return warnings


def template_payload(template: ShotTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "tags": template.tags or [],
        "shot_type": template.shot_type,
        "camera_movement": template.camera_movement,
        "lighting": template.lighting,
        "visual_style": template.visual_style,
        "color_palette": template.color_palette or [],
        "prompt_template": template.prompt_template,
        "negative_prompt": template.negative_prompt,
        "transition": template.transition,
        "remake_notes": template.remake_notes,
        "source_project_id": template.source_project_id,
        "source_shot_index": template.source_shot_index,
        "created_at": template.created_at.isoformat()
        if template.created_at
        else None,
        "updated_at": template.updated_at.isoformat()
        if template.updated_at
        else None,
    }
