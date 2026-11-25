"""Token usage and approximate cost summaries.

The application stores token counts produced by the LLM gateway. This module
never invents a provider bill: it only multiplies those counts by explicitly
configured per-million-token prices.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def estimate_usage(metrics: dict | None, settings: Settings) -> dict:
    """Return token totals and an optional, clearly labelled cost estimate."""
    metrics = metrics or {}
    calls = _as_int(metrics.get("calls"))
    prompt_tokens = _as_int(metrics.get("prompt_tokens"))
    completion_tokens = _as_int(metrics.get("completion_tokens"))
    input_price = float(settings.llm_input_price_per_million or 0)
    output_price = float(settings.llm_output_price_per_million or 0)
    priced = input_price > 0 or output_price > 0
    estimated_cost = None
    if priced:
        estimated_cost = round(
            prompt_tokens / 1_000_000 * input_price
            + completion_tokens / 1_000_000 * output_price,
            6,
        )
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
