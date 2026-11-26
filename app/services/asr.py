"""Speech-to-text provider integration used by full and targeted analysis pipelines."""

import logging
from pathlib import Path

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)


def transcribe(audio_path: Path, settings: Settings) -> list[dict]:
    """Dispatch to the configured ASR provider and return timed text segments."""
    provider = settings.asr_provider.lower().strip()
    if provider in ("", "none") or not audio_path.exists():
        return []
    if provider in {"openai", "openai-compatible", "compatible", "dashscope", "deepseek"}:
        return _transcribe_openai(audio_path, settings)
    logger.warning("unknown ASR provider: %s", provider)
    return []


def _transcribe_openai(audio_path: Path, settings: Settings) -> list[dict]:
    """Call an OpenAI-compatible transcription endpoint, returning ``[]`` on failure."""
    api_key = settings.asr_api_key or settings.llm_api_key
    if not api_key:
        logger.warning("ASR skipped: missing api key")
        return []

    url = settings.asr_base_url.rstrip("/") + "/audio/transcriptions"
    try:
        with httpx.Client(timeout=settings.request_timeout_s) as client:
            with audio_path.open("rb") as handle:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={"model": settings.asr_model, "response_format": "verbose_json"},
                    files={"file": (audio_path.name, handle, "audio/wav")},
                )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("ASR request failed: %s", exc)
        return []

    segments: list[dict] = []
    for item in payload.get("segments") or []:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": float(item.get("start") or 0.0),
                "end": float(item.get("end") or 0.0),
                "text": text,
            }
        )
    if not segments and payload.get("text"):
        segments.append({"start": 0.0, "end": 0.0, "text": payload["text"].strip()})
    return segments
