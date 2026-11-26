"""Token usage and approximate cost summaries.

The application stores token counts produced by the LLM gateway. This module
never invents a provider bill: it only multiplies those counts by explicitly
configured per-million-token prices.
"""

from __future__ import annotations

import math
from typing import Any

from ..config import Settings


def _as_int(value: Any) -> int:
    """Coerce arbitrary metrics to a non-negative integer."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _priced_amount(
    prompt_tokens: int,
    completion_tokens: int,
    settings: Settings,
) -> float | None:
    """Apply configured per-million-token prices, or return ``None`` when unpriced."""
    input_price = float(settings.llm_input_price_per_million or 0)
    output_price = float(settings.llm_output_price_per_million or 0)
    if input_price <= 0 and output_price <= 0:
        return None
    return round(
        prompt_tokens / 1_000_000 * input_price
        + completion_tokens / 1_000_000 * output_price,
        6,
    )


def estimate_usage(metrics: dict | None, settings: Settings) -> dict:
    """Return token totals and an optional, clearly labelled cost estimate."""
    metrics = metrics or {}
    calls = _as_int(metrics.get("calls"))
    prompt_tokens = _as_int(metrics.get("prompt_tokens"))
    completion_tokens = _as_int(metrics.get("completion_tokens"))
    input_price = float(settings.llm_input_price_per_million or 0)
    output_price = float(settings.llm_output_price_per_million or 0)
    estimated_cost = _priced_amount(prompt_tokens, completion_tokens, settings)
    priced = estimated_cost is not None
    return {
        "calls": calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "priced": priced,
        "estimated_cost": estimated_cost,
        "currency": (settings.cost_currency or "USD").upper(),
        "input_price_per_million": input_price,
        "output_price_per_million": output_price,
        "model": settings.llm_model,
        "vision_model": settings.vision_model or settings.llm_model,
        "note": (
            "按配置单价估算，不代表供应商账单"
            if priced
            else "未配置模型单价，仅展示 token 用量"
        ),
    }


def estimate_project_cost(
    video_duration: float,
    estimated_shots: int | None,
    settings: Settings,
) -> dict:
    """Rough pre-analysis estimate with transparent token assumptions.

    This is intentionally not a provider bill. It models one vision call per
    shot using configurable average token counts, then applies the configured
    per-million prices. ASR and real video-generation charges are excluded.
    """

    duration = max(0.1, float(video_duration or 0))
    max_shots = max(1, int(settings.max_shots or 1))
    seconds_per_shot = max(0.5, float(settings.cost_estimate_seconds_per_shot or 3.5))
    prompt_per_shot = max(1, int(settings.cost_estimate_prompt_tokens_per_shot or 1))
    completion_per_shot = max(
        0, int(settings.cost_estimate_completion_tokens_per_shot or 0)
    )

    if estimated_shots is None:
        requested_shots = max(1, math.ceil(duration / seconds_per_shot))
        shot_count_source = "heuristic"
    else:
        requested_shots = max(1, int(estimated_shots))
        shot_count_source = "manual"
    shots = min(max_shots, requested_shots)
    prompt_tokens = shots * prompt_per_shot
    completion_tokens = shots * completion_per_shot

    usage = estimate_usage(
        {
            "calls": shots,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        settings,
    )
    priced = bool(usage["priced"])
    vision_cost = usage["estimated_cost"]
    text_cost = 0.0 if vision_cost is not None else None
    total_cost = vision_cost
    provider = (settings.llm_provider or "mock").strip().lower()

    suggestions: list[str] = []
    if provider == "mock":
        suggestions.append(
            "当前 LLM_PROVIDER=mock，不会产生供应商费用；此预估用于接入真实模型前的规划。"
        )
    if not priced:
        suggestions.append(
            "未配置模型单价；设置 LLM_INPUT_PRICE_PER_MILLION 和 "
            "LLM_OUTPUT_PRICE_PER_MILLION 后可计算估算金额。"
        )
    if shots < requested_shots:
        suggestions.append(
            f"请求的 {requested_shots} 镜已按 MAX_SHOTS={max_shots} 上限估算。"
        )
    if shots > 12:
        target = 12
        saved = 1 - target / shots
        suggestions.append(
            f"当前按 {shots} 镜估算；将 MAX_SHOTS 调整到 {target} "
            f"可减少约 {saved:.0%} 的视觉分析 token。"
        )
    if duration > 90:
        suggestions.append("视频较长，建议先用核心片段试跑，确认拆镜和风格后再分析全片。")
    if (settings.asr_provider or "none").strip().lower() not in ("", "none"):
        suggestions.append("ASR 转写按语音供应商单独计费，未包含在本估算中。")
    suggestions.append("真实视频生成费用不包含在本估算中，将在平台接入后另行计算。")

    note = (
        "按配置单价估算，不代表供应商账单；未包含 ASR 和真实视频生成费用"
        if priced
        else "未配置模型单价，仅展示 token 估算；未包含 ASR 和真实视频生成费用"
    )
    return {
        "video_duration": round(duration, 2),
        "estimated_shots": shots,
        "requested_shots": requested_shots,
        "shot_count_source": shot_count_source,
        "estimated_seconds_per_shot": round(duration / shots, 2),
        "provider": provider,
        "billable": priced and provider != "mock",
        "assumptions": {
            "seconds_per_shot": seconds_per_shot,
            "prompt_tokens_per_shot": prompt_per_shot,
            "completion_tokens_per_shot": completion_per_shot,
            "max_shots": max_shots,
        },
        "cost": {
            **usage,
            "shot_count": shots,
            "vision_cost": vision_cost,
            "text_cost": text_cost,
            "total_cost": total_cost,
            "note": note,
        },
        "video_generation_cost": {
            "priced": False,
            "note": "真实视频生成费用将在平台接入后计算",
        },
        "suggestions": suggestions,
    }
