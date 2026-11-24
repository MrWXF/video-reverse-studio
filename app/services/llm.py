import threading

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from ..config import Settings


class LLMGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def enabled(self) -> bool:
        return self.settings.llm_provider.lower() != "mock" and bool(self.settings.llm_api_key)

    def chat_model(self, vision: bool = False) -> BaseChatModel | None:
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
        usage = getattr(message, "usage_metadata", None) or {}
        with self._lock:
            self.calls += 1
            self.prompt_tokens += int(usage.get("input_tokens") or 0)
            self.completion_tokens += int(usage.get("output_tokens") or 0)

    def stats(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
            }
