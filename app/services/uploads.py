"""Upload filename, content-signature, size, and text-sanitization helpers."""

import re
from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class UploadValidationError(ValueError):
    """The uploaded file failed signature or format validation."""

    pass


class UploadTooLargeError(UploadValidationError):
    """The uploaded file exceeded the configured byte limit."""

    pass


def safe_filename(name: str, fallback: str = "未命名") -> str:
    """Return a display-safe basename without control characters."""
    normalized = (name or "").replace("\\", "/")
    basename = Path(normalized).name.strip()
    basename = _CONTROL_CHARS.sub("", basename).strip(" .")
    return basename[:200] or fallback


def clean_text(value: str, *, default: str = "", limit: int = 200) -> str:
    """Strip control characters, trim text, and apply a fallback and length limit."""
    text = _CONTROL_CHARS.sub("", value or "").strip()
    return (text or default)[:limit]


def validate_video_header(suffix: str, header: bytes) -> None:
    """Check the container signature instead of trusting the extension."""
    if len(header) < 12:
        raise UploadValidationError("上传的文件不是有效的视频容器")
    suffix = suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v"}:
        if b"ftyp" not in header[:64]:
            raise UploadValidationError("文件内容与 MP4/MOV 扩展名不匹配")
        return
    if suffix in {".webm", ".mkv"}:
        if not header.startswith(b"\x1aE\xdf\xa3"):
            raise UploadValidationError("文件内容与 WebM/MKV 扩展名不匹配")
        return
    if suffix == ".avi":
        if not (header.startswith(b"RIFF") and header[8:12] == b"AVI "):
            raise UploadValidationError("文件内容与 AVI 扩展名不匹配")
        return
    raise UploadValidationError(f"不支持的视频格式：{suffix or '未知'}")


def save_validated_upload(upload, target: Path, limit_bytes: int) -> int:
    """Stream an upload to disk after validating its container signature."""
    header = upload.file.read(64)
    if not header:
        raise UploadValidationError("上传的文件为空")
    validate_video_header(target.suffix, header)
    written = len(header)
    if written > limit_bytes:
        raise UploadTooLargeError("上传文件超过大小限制")
    with target.open("wb") as handle:
        handle.write(header)
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > limit_bytes:
                raise UploadTooLargeError("上传文件超过大小限制")
            handle.write(chunk)
    return written
