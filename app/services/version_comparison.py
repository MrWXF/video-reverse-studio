"""Read-only comparison between two prompt-version snapshots."""

from __future__ import annotations

from collections import Counter

from ..models import PromptVersion
from ..schemas import PromptPlan

SHOT_FIELD_LABELS = {
    "start_s": "开始时间",
    "end_s": "结束时间",
    "duration": "时长",
    "shot_type": "景别",
    "camera_movement": "运镜",
    "subject": "主体",
    "action": "动作",
    "scene": "场景",
    "lighting": "光线",
    "color_palette": "色板",
    "prompt": "Prompt",
    "negative_prompt": "Negative Prompt",
    "transition": "转场",
    "remake_notes": "复刻备注",
    "source_shot_index": "来源镜头",
    "locked_fields": "锁定字段",
}

PLAN_FIELD_LABELS = {
    "title": "方案标题",
    "summary": "方案摘要",
    "target_model": "目标模型",
    "language": "Prompt 语言",
    "duration_s": "总时长",
    "aspect_ratio": "画幅",
    "global_style": "全局风格",
    "assumptions": "制作假设",
    "warnings": "风险提示",
}

BRIEF_FIELD_LABELS = {
    "title": "标题",
    "idea": "创意描述",
    "target_model": "目标模型",
    "language": "语言",
    "duration_s": "时长",
    "aspect_ratio": "画幅",
    "shot_count": "镜头数",
    "style": "风格",
    "mood": "氛围",
    "audience": "受众",
    "negative_prompt": "反向提示",
    "constraints": "约束",
    "reference_project_id": "参考项目",
    "reference_mode": "参考模式",
}

ENTITY_FIELD_LABELS = {
    "characters": "角色",
    "products": "产品",
    "wardrobe": "服装",
    "scenes": "场景资产",
    "consistency_rules": "一致性规则",
}


def _version_meta(version: PromptVersion) -> dict:
    """Serialize the version metadata shown on both sides of a comparison."""
    plan = version.plan_json or {}
    return {
        "id": version.id,
        "version": version.version,
        "source": version.source,
        "title": version.title,
        "shot_count": len(plan.get("shots") or []),
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def _top_level_changes(
    left: dict,
    right: dict,
    labels: dict[str, str],
    excluded: set[str] | None = None,
) -> list[dict]:
    """Return changed top-level fields with labels and both values."""
    excluded = excluded or set()
    keys = sorted((set(left) | set(right)) - excluded)
    return [
        {
            "field": key,
            "label": labels.get(key, key),
            "left": left.get(key),
            "right": right.get(key),
        }
        for key in keys
        if left.get(key) != right.get(key)
    ]


def _field_diffs(left: dict, right: dict) -> list[dict]:
    """Return changed shot fields in the canonical comparison order."""
    return [
        {
            "field": field,
            "label": label,
            "left": left.get(field),
            "right": right.get(field),
        }
        for field, label in SHOT_FIELD_LABELS.items()
        if left.get(field) != right.get(field)
    ]


def build_version_comparison(
    left_version: PromptVersion,
    right_version: PromptVersion,
) -> dict:
    """Compare two validated snapshots by plan, entity, and shot-level changes."""
    try:
        left_plan = PromptPlan.model_validate(left_version.plan_json or {})
        right_plan = PromptPlan.model_validate(right_version.plan_json or {})
    except Exception as exc:
        raise ValueError("版本快照结构无效，无法比较") from exc

    left_shots = {
        shot.index: shot.model_dump(mode="json") for shot in left_plan.shots
    }
    right_shots = {
        shot.index: shot.model_dump(mode="json") for shot in right_plan.shots
    }
    indexes = sorted(set(left_shots) | set(right_shots))
    shot_diffs: list[dict] = []
    field_totals: Counter[str] = Counter()
    added = removed = modified = unchanged = 0

    for index in indexes:
        left = left_shots.get(index)
        right = right_shots.get(index)
        if left is None:
            status = "added"
            added += 1
            fields: list[dict] = []
        elif right is None:
            status = "removed"
            removed += 1
            fields = []
        else:
            fields = _field_diffs(left, right)
            status = "modified" if fields else "unchanged"
            if fields:
                modified += 1
            else:
                unchanged += 1
            for item in fields:
                field_totals[item["field"]] += 1

        shot_diffs.append(
            {
                "index": index,
                "status": status,
                "changed_fields": [item["field"] for item in fields],
                "fields": fields,
                "left": left,
                "right": right,
            }
        )

    left_plan_data = left_plan.model_dump(mode="json")
    right_plan_data = right_plan.model_dump(mode="json")
    plan_changes = _top_level_changes(
        left_plan_data,
        right_plan_data,
        PLAN_FIELD_LABELS,
        excluded={"shots", "generated_at"},
    )
    brief_changes = _top_level_changes(
        left_version.brief_json or {},
        right_version.brief_json or {},
        BRIEF_FIELD_LABELS,
        excluded={"entity_bible"},
    )
    entity_changes = _top_level_changes(
        left_version.entity_bible_json or {},
        right_version.entity_bible_json or {},
        ENTITY_FIELD_LABELS,
    )
    changed_shots = added + removed + modified
    denominator = max(len(left_shots), len(right_shots), 1)

    return {
        "left": _version_meta(left_version),
        "right": _version_meta(right_version),
        "summary": {
            "left_shots": len(left_shots),
            "right_shots": len(right_shots),
            "added_shots": added,
            "removed_shots": removed,
            "modified_shots": modified,
            "unchanged_shots": unchanged,
            "changed_shots": changed_shots,
            "field_changes": sum(field_totals.values()),
            "change_ratio": round(changed_shots / denominator, 4),
            "duration_delta": round(right_plan.duration_s - left_plan.duration_s, 3),
            "has_changes": bool(changed_shots or plan_changes or brief_changes or entity_changes),
        },
        "field_totals": [
            {
                "field": field,
                "label": SHOT_FIELD_LABELS.get(field, field),
                "count": count,
            }
            for field, count in sorted(
                field_totals.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "plan_changes": plan_changes,
        "brief_changes": brief_changes,
        "entity_changes": entity_changes,
        "shots": shot_diffs,
        "note": "差异基于两个版本快照，不会修改当前方案。",
    }
