"""Configured text-model gateway with usage accounting and optional mock fallback."""

import threading

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ..config import Settings


class LLMGateway:
    """Create configured chat models and accumulate per-request token usage."""

    def __init__(self, settings: Settings):
        """Store settings and initialize thread-safe usage counters."""
        self.settings = settings
        self._lock = threading.Lock()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._degradation_reasons: list[str] = []

    @property
    def enabled(self) -> bool:
        """Return whether a non-mock provider and API key are configured."""
        return self.settings.llm_provider.lower() != "mock" and bool(self.settings.llm_api_key)

    def chat_model(self, vision: bool = False) -> BaseChatModel | None:
        """Create a zero-temperature chat model for text or vision analysis."""
        if not self.enabled:
            return None
        model = self.settings.llm_model
        if vision and self.settings.vision_model:
            model = self.settings.vision_model
        kwargs = {
            "model": model,
            "api_key": self.settings.llm_api_key,
            "temperature": 0,
            "timeout": self.settings.request_timeout_s,
            "max_retries": max(1, self.settings.retry_max_attempts - 1),
        }
        if self.settings.llm_base_url:
            kwargs["base_url"] = self.settings.llm_base_url
        return ChatOpenAI(**kwargs)

    def record_usage(self, message) -> None:
        """Accumulate token usage from one provider response."""
        usage = getattr(message, "usage_metadata", None) or {}
        with self._lock:
            self.calls += 1
            self.prompt_tokens += int(usage.get("input_tokens") or 0)
            self.completion_tokens += int(usage.get("output_tokens") or 0)

    def record_degradation(self, reason: str) -> None:
        """Record one transparent fallback reason without duplicating messages."""
        cleaned = (reason or "").strip()
        if not cleaned:
            return
        with self._lock:
            if cleaned not in self._degradation_reasons and len(self._degradation_reasons) < 10:
                self._degradation_reasons.append(cleaned[:300])

    def stats(self) -> dict:
        """Return a consistent snapshot of call and token counters."""
        with self._lock:
            return {
                "calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
            }

    def execution_metadata(self, *, asr_status: str | None = None) -> dict:
        """Return explicit execution-mode and degradation metadata for API clients."""
        with self._lock:
            reasons = list(self._degradation_reasons)
        degraded = bool(reasons)
        mode = "degraded" if degraded else ("live" if self.enabled else "mock")
        payload = {
            "analysis_mode": mode,
            "degraded": degraded,
            "degradation_reasons": reasons,
            "llm_enabled": self.enabled,
        }
        if asr_status is not None:
            payload["asr_status"] = asr_status
        return payload
