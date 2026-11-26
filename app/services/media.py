"""ffmpeg/ffprobe helpers for probing, segmentation, keyframes, and audio extraction."""

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings

logger = logging.getLogger(__name__)


@dataclass
class VideoMeta:
    """Basic video metadata required by segmentation and prompt analysis."""

    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a media command with decoded output and a hard timeout."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def resolve_ffmpeg(configured: str = "ffmpeg") -> str | None:
    """Resolve ffmpeg from PATH or the bundled imageio-ffmpeg package."""
    found = shutil.which(configured)
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def resolve_ffprobe(configured: str = "ffprobe") -> str | None:
    """Resolve ffprobe from PATH or beside the resolved ffmpeg executable."""
    found = shutil.which(configured)
    if found:
        return found
    ffmpeg = resolve_ffmpeg("ffmpeg")
    if not ffmpeg:
        return None
    suffix = "ffprobe.exe" if ffmpeg.lower().endswith(".exe") else "ffprobe"
    candidate = Path(ffmpeg).with_name(suffix)
    return str(candidate) if candidate.exists() else None


def _parse_rate(value: str | None) -> float:
    """Parse ffprobe's fractional or decimal frame-rate notation."""
    if not value:
        return 0.0
    if "/" in value:
        num, _, den = value.partition("/")
        try:
            return float(num) / float(den) if float(den) else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def probe(path: Path, settings: Settings) -> VideoMeta:
    """Read duration, dimensions, and FPS, falling back to ffmpeg stderr parsing."""
    ffprobe = resolve_ffprobe(settings.ffprobe_bin)
    if ffprobe:
        cmd = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            completed = _run(cmd, timeout=60)
            data = json.loads(completed.stdout or "{}")
            stream = (data.get("streams") or [{}])[0]
            container = data.get("format") or {}
            return VideoMeta(
                duration=float(container.get("duration") or 0.0),
                width=int(stream.get("width") or 0),
                height=int(stream.get("height") or 0),
                fps=_parse_rate(stream.get("avg_frame_rate")),
            )
        except Exception as exc:
            logger.warning("ffprobe failed, falling back to ffmpeg: %s", exc)

    ffmpeg = resolve_ffmpeg(settings.ffmpeg_bin)
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请安装 imageio-ffmpeg 或系统 ffmpeg")

    completed = _run([ffmpeg, "-hide_banner", "-i", str(path)], timeout=60)
    text = completed.stderr or ""
    duration = 0.0
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if match:
        duration = (
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + float(match.group(3))
        )
    size = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    fps_match = re.search(r"([\d.]+)\s*fps", text)
    return VideoMeta(
        duration=duration,
        width=int(size.group(1)) if size else 0,
        height=int(size.group(2)) if size else 0,
        fps=float(fps_match.group(1)) if fps_match else 0.0,
    )


def merge_short_shots(
    boundaries: list[float], min_seconds: float
) -> list[tuple[float, float]]:
    """Remove interior cut points that would create shots below the minimum duration."""
    points = sorted({round(point, 3) for point in boundaries})
    if len(points) < 2:
        return []
    merged = [points[0]]
    for point in points[1:-1]:
        if point - merged[-1] >= min_seconds:
            merged.append(point)
    if len(merged) > 1 and points[-1] - merged[-1] < min_seconds:
        merged.pop()
    merged.append(points[-1])
    return [(merged[i], merged[i + 1]) for i in range(len(merged) - 1)]


def cap_shots(
    segments: list[tuple[float, float]], max_shots: int
) -> list[tuple[float, float]]:
    """Evenly resplit a timeline when scene detection exceeds the shot limit."""
    if not segments or len(segments) <= max_shots:
        return segments
    start = segments[0][0]
    end = segments[-1][1]
    step = (end - start) / max_shots
    return [(start + i * step, start + (i + 1) * step) for i in range(max_shots)]


def fallback_segments(
    duration: float, max_shots: int, target_seconds: float = 6.0
) -> list[tuple[float, float]]:
    """Create evenly spaced fallback segments when scene detection cannot run."""
    if duration <= 0:
        return [(0.0, target_seconds)]
    count = max(1, min(max_shots, round(duration / target_seconds) or 1))
    step = duration / count
    return [(i * step, (i + 1) * step) for i in range(count)]


def detect_shots(path: Path, meta: VideoMeta, settings: Settings) -> list[tuple[float, float]]:
    """Detect scene cuts with ffmpeg and normalize them into valid shot intervals."""
    ffmpeg = resolve_ffmpeg(settings.ffmpeg_bin)
    cuts: list[float] = []
    if ffmpeg and meta.duration > 0:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-an",
            "-filter:v",
            f"select='gt(scene,{settings.scene_threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = _run(cmd, timeout=600)
            cuts = [
                float(value)
                for value in re.findall(r"pts_time:\s*([0-9.]+)", completed.stderr or "")
            ]
        except Exception as exc:
            logger.warning("scene detection failed: %s", exc)

    if not cuts or meta.duration <= 0:
        return fallback_segments(meta.duration, settings.max_shots)

    boundaries = [0.0]
    boundaries.extend(sorted({cut for cut in cuts if 0.15 < cut < meta.duration - 0.15}))
    boundaries.append(meta.duration)
    segments = merge_short_shots(boundaries, settings.min_shot_seconds)
    if not segments:
        segments = fallback_segments(meta.duration, settings.max_shots)
    return cap_shots(segments, settings.max_shots)


def extract_keyframe(ffmpeg: str, video: Path, timestamp: float, output: Path) -> None:
    """Extract and downscale one JPEG keyframe, raising when ffmpeg produces no file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "scale=768:-2",
        "-q:v",
        "3",
        str(output),
    ]
    completed = _run(cmd, timeout=120)
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(f"关键帧抽取失败: {(completed.stderr or '')[-300:]}")


def extract_audio(ffmpeg: str, video: Path, output: Path) -> None:
    """Extract mono 16 kHz PCM audio for speech-to-text providers."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output),
    ]
    completed = _run(cmd, timeout=300)
    if completed.returncode != 0 or not output.exists():
        raise RuntimeError(f"音频抽取失败: {(completed.stderr or '')[-300:]}")
