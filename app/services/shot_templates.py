"""Reusable shot templates and template application to prompt plans."""

from __future__ import annotations

import re

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
TEXT_FIELDS = (
    "shot_type",
    "camera_movement",
    "lighting",
    "transition",
    "prompt_template",
    "negative_prompt",
    "remake_notes",
)
PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


def _clean_tags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for value in values:
        tag = str(value or "").strip()[:50]
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:20]


def normalize_tags(values: list[str] | None) -> list[str]:
    return _clean_tags(values or [])


def placeholders_in(value: str | None) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(value or "")))


def _context_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_context_text(item) for item in value if _context_text(item))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _shot_context(plan: PromptPlan, shot) -> dict:
    context = {
        "title": plan.title,
        "summary": plan.summary,
        "target_model": plan.target_model,
        "language": _context_text(plan.language),
        "duration_s": plan.duration_s,
        "aspect_ratio": plan.aspect_ratio,
        "global_style": plan.global_style,
    }
    for key, value in shot.model_dump(mode="json").items():
        context[key] = _context_text(value)
    context["index"] = context.get("index", "")
    context["shot_index"] = context.get("index", "")
    return context


def _render_placeholders(value: str, context: dict, warnings: list[str]) -> str:
    unknown: list[str] = []
    empty: list[str] = []

    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in context:
            unknown.append(key)
            return match.group(0)
        rendered = _context_text(context[key])
        if rendered == "":
            empty.append(key)
        return rendered

    rendered = PLACEHOLDER_RE.sub(replace, value)
    for key in dict.fromkeys(unknown):
        warnings.append("模板包含未知占位符 {{" + key + "}}，已原样保留。")
    for key in dict.fromkeys(empty):
        warnings.append("模板占位符 {{" + key + "}} 没有可用值，已替换为空。")
    return rendered


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
        prompt_template=(
            payload.prompt_template
            if payload.prompt_template is not None
            else str(analysis.get("prompt") or "")
        ),
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
        context = _shot_context(plan, shot)
        for field in requested:
            value = getattr(
                template,
                "prompt_template" if field == "prompt" else field,
                None,
            )
            if value in (None, "", []):
                continue
            if isinstance(value, str) and "{{" in value:
                value = _render_placeholders(value, context, warnings)
            setattr(shot, field, value)
            applied += 1
    if not applied:
        warnings.append("模板没有可应用的内容")
    return list(dict.fromkeys(warnings))


def template_payload(template: ShotTemplate) -> dict:
    placeholders = placeholders_in(
        " ".join(str(getattr(template, field) or "") for field in TEXT_FIELDS)
    )
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
        "has_placeholders": bool(placeholders),
        "placeholders": placeholders,
    }
