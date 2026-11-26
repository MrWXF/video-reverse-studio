"""Provider-neutral video generation adapters.

Only the mock adapter is implemented until a real provider's API has been
verified. Credentials are read from server-side settings and are never accepted
from or returned to the browser.
"""

from __future__ import annotations

import html
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from .media import resolve_ffmpeg

SUPPORTED_ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "21:9")


class GenerationProviderError(RuntimeError):
    """The configured provider cannot run in this deployment."""


class GenerationInputError(ValueError):
    """A shot cannot be submitted to the provider."""


@dataclass(frozen=True)
class VideoGenerationRequest:
    """Provider-neutral request for generating one shot."""

    shot_index: int
    title: str
    prompt: str
    negative_prompt: str = ""
    duration_s: float = 5.0
    aspect_ratio: str = "16:9"
    model: str = ""


@dataclass
class GeneratedVideo:
    """Generated media bytes and metadata ready for local persistence."""

    data: bytes
    extension: str
    media_type: str
    provider_job_id: str
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class VideoGenerationAdapter(ABC):
    """Interface implemented by local mock and future remote video providers."""

    name = "base"
    label = "Base"

    def __init__(self, settings: Settings) -> None:
        """Store deployment settings used by provider implementations."""
        self.settings = settings

    @abstractmethod
    def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
        """Generate one shot and return bytes ready for local persistence."""

    def cancel(self, provider_job_id: str) -> None:
        """Best-effort provider cancellation for asynchronous providers."""
        return None


class MockVideoGenerationAdapter(VideoGenerationAdapter):
    """Local placeholder generator used to validate the full product flow."""

    name = "mock"
    label = "Mock 本地演示"

    def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
        """Render a local MP4 placeholder, falling back to a static SVG on failure."""
        if not request.prompt.strip():
            raise GenerationInputError(f"镜头 {request.shot_index} 没有可用的 Prompt")
        warnings = ["Mock 模式：生成的是本地占位素材，不代表真实视频模型效果。"]
        metadata = {"mode": "mock", "aspect_ratio": request.aspect_ratio}
        try:
            ffmpeg = resolve_ffmpeg(self.settings.ffmpeg_bin)
            if not ffmpeg:
                raise RuntimeError("ffmpeg is unavailable")
            data = self._render_mp4(ffmpeg, request)
            metadata["rendered"] = "mp4"
            extension, media_type = "mp4", "video/mp4"
        except Exception:
            data = self._render_svg(request)
            metadata["rendered"] = "svg"
            extension, media_type = "svg", "image/svg+xml"
            warnings.append("ffmpeg 不可用，已返回可预览的静态占位图。")
        return GeneratedVideo(
            data=data,
            extension=extension,
            media_type=media_type,
            provider_job_id=f"mock-{uuid.uuid4().hex[:12]}",
            warnings=warnings,
            metadata=metadata,
        )

    def _render_mp4(self, ffmpeg: str, request: VideoGenerationRequest) -> bytes:
        """Render a short synthetic MP4 test pattern with ffmpeg."""
        width, height = {
            "9:16": (360, 640),
            "16:9": (640, 360),
            "1:1": (480, 480),
            "4:3": (640, 480),
            "21:9": (840, 360),
        }.get(request.aspect_ratio, (640, 360))
        duration = max(1.0, min(float(request.duration_s or 1.0), 5.0))
        with tempfile.TemporaryDirectory(prefix="reelreverse-mock-") as directory:
            output = Path(directory) / "mock.mp4"
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=s={width}x{height}:r=24:d={duration:.2f}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError("mock ffmpeg render failed")
            return output.read_bytes()

    def _render_svg(self, request: VideoGenerationRequest) -> bytes:
        """Render an escaped SVG placeholder when ffmpeg is unavailable."""
        title = html.escape((request.title or "Mock Video")[:60])
        prompt = html.escape((request.prompt or "")[:140])
        shot = html.escape(f"SHOT {request.shot_index:02d}")
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#111827"/><stop offset="1" stop-color="#4338ca"/></linearGradient></defs>
<rect width="960" height="540" fill="url(#g)"/><circle cx="790" cy="90" r="170" fill="#f59e0b" opacity=".22"/>
<text x="64" y="92" fill="#fbbf24" font-family="Arial" font-size="24" font-weight="700">{shot} / MOCK OUTPUT</text>
<text x="64" y="188" fill="#ffffff" font-family="Arial" font-size="48" font-weight="700">{title}</text>
<foreignObject x="64" y="235" width="760" height="180"><div xmlns="http://www.w3.org/1999/xhtml" style="font:24px Arial;color:#d1d5db;line-height:1.5">{prompt}</div></foreignObject>
<text x="64" y="490" fill="#9ca3af" font-family="Arial" font-size="20">ReelReverse mock asset · {html.escape(request.aspect_ratio)} · {request.duration_s:.1f}s</text>
</svg>"""
        return svg.encode("utf-8")


def create_adapter(settings: Settings) -> VideoGenerationAdapter:
    """Create the configured provider adapter or fail with a capability error."""
    provider = (settings.video_provider or "mock").strip().lower()
    if provider == "mock":
        return MockVideoGenerationAdapter(settings)
    raise GenerationProviderError(
        f"视频生成平台 {provider} 尚未接入，请先完成正式 API 验证并配置适配器"
    )


def capabilities(settings: Settings) -> dict:
    """Describe provider readiness and supported generation limits without secrets."""
    provider = (settings.video_provider or "mock").strip().lower()
    mock = provider == "mock"
    return {
        "provider": provider,
        "label": "Mock 本地演示" if mock else provider,
        "ready": mock,
        "mode": "mock" if mock else "unavailable",
        "reason": "" if mock else "当前平台适配器尚未完成 API 验证",
        "model": settings.video_model,
        "aspect_ratios": list(SUPPORTED_ASPECT_RATIOS),
        "max_active_jobs": settings.max_active_generation_jobs,
        "credential_configured": bool(settings.video_api_key),
    }
