"""Range-aware file responses for browser media playback."""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from email.utils import formatdate
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response, StreamingResponse

CHUNK_SIZE = 64 * 1024


class RangeNotSatisfiable(ValueError):
    """The requested byte range is invalid for the current file."""

    pass


def _parse_range(value: str, size: int) -> tuple[int, int]:
    """Parse a single HTTP byte-range header into inclusive offsets."""
    unit, separator, raw = value.partition("=")
    if separator != "=" or unit.strip().lower() != "bytes" or "," in raw:
        raise RangeNotSatisfiable(value)
    start_text, dash, end_text = raw.strip().partition("-")
    if dash != "-" or (not start_text and not end_text):
        raise RangeNotSatisfiable(value)
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            suffix = int(end_text)
            if suffix <= 0:
                raise RangeNotSatisfiable(value)
            start = max(size - suffix, 0)
            end = size - 1
    except ValueError as exc:
        raise RangeNotSatisfiable(value) from exc
    if size <= 0 or start < 0 or start >= size or end < start:
        raise RangeNotSatisfiable(value)
    return start, min(end, size - 1)


def _file_chunks(path: Path, start: int, length: int) -> Iterator[bytes]:
    """Yield a bounded file region in streaming chunks."""
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def range_file_response(path: Path, request: Request) -> Response:
    """Return a full or partial file response with browser-seekable range headers."""
    size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    common_headers = {
        "Accept-Ranges": "bytes",
        "Last-Modified": formatdate(path.stat().st_mtime, usegmt=True),
    }
    range_header = request.headers.get("range")
    if not range_header:
        headers = {**common_headers, "Content-Length": str(size)}
        return StreamingResponse(
            _file_chunks(path, 0, size),
            media_type=media_type,
            headers=headers,
        )
    try:
        start, end = _parse_range(range_header, size)
    except RangeNotSatisfiable:
        return Response(
            status_code=416,
            headers={
                **common_headers,
                "Content-Range": f"bytes */{size}",
                "Content-Length": "0",
            },
        )
    length = end - start + 1
    headers = {
        **common_headers,
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(length),
    }
    return StreamingResponse(
        _file_chunks(path, start, length),
        status_code=206,
        media_type=media_type,
        headers=headers,
    )
