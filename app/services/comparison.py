from ..schemas import PromptPlan, Recipe


def _palette(shots) -> list[str]:
    colors: list[str] = []
    for shot in shots:
        for color in getattr(shot, "color_palette", []) or []:
            normalized = str(color).strip().lower()
            if normalized and normalized not in colors:
                colors.append(normalized)
    return colors


def _overlap(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    left_set = {item.strip().lower() for item in left if item}
    right_set = {item.strip().lower() for item in right if item}
    return round(len(left_set & right_set) / len(left_set | right_set), 3)


def build_reference_comparison(
    reference_snapshot: dict,
    mode: str,
    plan: PromptPlan,
) -> dict:
    recipe = Recipe.model_validate(reference_snapshot["recipe"])
    reference_shots = {shot.index: shot for shot in recipe.shots}
    generated_shots = plan.shots
    reference_palette = _palette(recipe.shots)
    generated_palette = _palette(generated_shots)

    pairs = []
    for shot in generated_shots:
        source = reference_shots.get(shot.source_shot_index or 0)
        if source is None:
            continue
        checks = {
            "shot_type": source.shot_type == shot.shot_type,
            "camera_movement": source.camera_movement == shot.camera_movement,
            "lighting": not source.lighting or source.lighting == shot.lighting,
            "duration": abs(source.duration - shot.duration)
            <= max(0.35, source.duration * 0.25),
        }
        matches = sum(1 for value in checks.values() if value)
        pairs.append(
            {
                "source_shot_index": source.index,
                "generated_shot_index": shot.index,
                "reference": {
                    "shot_type": source.shot_type,
                    "camera_movement": source.camera_movement,
                    "lighting": source.lighting,
                    "duration": source.duration,
                    "prompt": source.prompt,
                },
                "generated": {
                    "shot_type": shot.shot_type,
                    "camera_movement": shot.camera_movement,
                    "lighting": shot.lighting,
                    "duration": shot.duration,
                    "prompt": shot.prompt,
                },
                "checks": checks,
                "match_score": round(matches / len(checks), 3),
            }
        )

    mapped_score = (
        round(sum(item["match_score"] for item in pairs) / len(pairs), 3)
        if pairs
        else 0.0
    )
    reference_style = next(
        (shot.visual_style for shot in recipe.shots if shot.visual_style), ""
    )
    return {
        "mode": mode,
        "reference_title": recipe.title,
        "generated_title": plan.title,
        "summary": {
            "reference_shots": len(recipe.shots),
            "generated_shots": len(generated_shots),
            "mapped_shots": len(pairs),
            "structure_match": mapped_score,
            "palette_overlap": _overlap(reference_palette, generated_palette),
        },
        "style": {
            "reference": reference_style,
            "generated": plan.global_style,
            "reference_palette": reference_palette[:8],
            "generated_palette": generated_palette[:8],
        },
        "shots": pairs,
    }
