from ..schemas import PromptPlan

_PROFILES: dict[str, dict] = {
    "generic": {
        "label": "通用模型",
        "max_prompt_chars": 2000,
        "max_negative_chars": 1000,
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "21:9"],
        "min_shot_seconds": 1.0,
        "max_shot_seconds": 30.0,
        "notes": "保持结构化描述，具体参数由生成平台决定。",
    },
    "veo": {
        "label": "Google Veo",
        "max_prompt_chars": 1200,
        "max_negative_chars": 500,
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "min_shot_seconds": 2.0,
        "max_shot_seconds": 8.0,
        "notes": "单镜头建议短而完整，优先写清主体动作、镜头运动和光线。",
    },
    "sora": {
        "label": "OpenAI Sora",
        "max_prompt_chars": 2000,
        "max_negative_chars": 800,
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "min_shot_seconds": 2.0,
        "max_shot_seconds": 20.0,
        "notes": "适合较完整的场景叙述，避免堆叠互相冲突的风格词。",
    },
    "runway": {
        "label": "Runway Gen-3",
        "max_prompt_chars": 1500,
        "max_negative_chars": 500,
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "min_shot_seconds": 2.0,
        "max_shot_seconds": 10.0,
        "notes": "突出单一动作和明确运镜，短镜头更容易保持一致性。",
    },
    "kling": {
        "label": "Kling",
        "max_prompt_chars": 2500,
        "max_negative_chars": 800,
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "min_shot_seconds": 2.0,
        "max_shot_seconds": 10.0,
        "notes": "适合中文制作团队复核，保留主体、动作、镜头和光影四类信息。",
    },
    "luma": {
        "label": "Luma Dream Machine",
        "max_prompt_chars": 1500,
        "max_negative_chars": 500,
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "21:9"],
        "min_shot_seconds": 2.0,
        "max_shot_seconds": 10.0,
        "notes": "自然语言描述优先，运镜不要同时叠加多个方向。",
    },
    "pika": {
        "label": "Pika",
        "max_prompt_chars": 1000,
        "max_negative_chars": 400,
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "min_shot_seconds": 1.0,
        "max_shot_seconds": 8.0,
        "notes": "Prompt 宜精简，优先保留主体、动作、场景和光线。",
    },
}

_ALIASES = {
    "google veo": "veo",
    "veo3": "veo",
    "runway gen-3": "runway",
    "gen-3": "runway",
    "dream machine": "luma",
    "openai sora": "sora",
}


def get_model_profile(name: str) -> dict:
    key = (name or "generic").strip().lower()
    key = _ALIASES.get(key, key)
    if key not in _PROFILES:
        key = "generic"
    return {"id": key, **_PROFILES[key]}


def model_profile_options() -> list[dict]:
    return [{"id": key, **value} for key, value in _PROFILES.items()]


def validate_prompt_plan(plan: PromptPlan, total_duration: float) -> list[str]:
    profile = plan.target_profile or get_model_profile(plan.target_model)
    warnings: list[str] = []
    max_prompt = int(profile.get("max_prompt_chars") or 0)
    max_negative = int(profile.get("max_negative_chars") or 0)

    over_prompt = [
        shot.index for shot in plan.shots if max_prompt and len(shot.prompt) > max_prompt
    ]
    if over_prompt:
        warnings.append(
            f"{profile.get('label', plan.target_model)} 单镜 Prompt 上限 {max_prompt} 字符；"
            f"镜头 {', '.join(map(str, over_prompt))} 超出，发布前建议压缩。"
        )
    over_negative = [
        shot.index
        for shot in plan.shots
        if max_negative and len(shot.negative_prompt) > max_negative
    ]
    if over_negative:
        warnings.append(
            f"{profile.get('label', plan.target_model)} 负向词上限 {max_negative} 字符；"
            f"镜头 {', '.join(map(str, over_negative))} 超出。"
        )
    supported = profile.get("aspect_ratios") or []
    if supported and plan.aspect_ratio not in supported:
        warnings.append(
            f"{profile.get('label', plan.target_model)} 不保证支持 {plan.aspect_ratio}，"
            f"可选：{', '.join(supported)}。"
        )
    short = [
        shot.index
        for shot in plan.shots
        if shot.duration < float(profile.get("min_shot_seconds") or 0)
    ]
    long = [
        shot.index
        for shot in plan.shots
        if shot.duration > float(profile.get("max_shot_seconds") or 1e9)
    ]
    if short or long:
        warnings.append(
            f"{profile.get('label', plan.target_model)} 单镜建议时长 "
            f"{profile.get('min_shot_seconds')}–{profile.get('max_shot_seconds')}s；"
            f"过短镜头：{short or '无'}，过长镜头：{long or '无'}。"
        )
    if total_duration <= 0:
        warnings.append("方案总时长为 0，请检查 Brief。")
    return warnings
