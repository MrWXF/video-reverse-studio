"""Remove credentials and local paths from user-visible error messages."""

import re
from pathlib import Path

from ..config import PROJECT_ROOT, Settings

_SECRET_PATTERNS = (
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1***"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "sk-***"),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"), r"\1***"),
    (re.compile(r"(?i)(password\s*[=:]\s*)[^\s,;]+"), r"\1***"),
)


def redact_text(
    value: object,
    settings: Settings | None = None,
    *,
    limit: int = 2000,
) -> str:
    """Remove local paths and credentials from user-visible error text."""
    text = str(value or "")
    roots: list[tuple[Path, str]] = [(PROJECT_ROOT, "<APP_ROOT>")]
    if settings is not None:
        roots.insert(0, (settings.data_dir, "<DATA_DIR>"))
    roots.append((Path.home(), "<HOME>"))

    for root, replacement in roots:
        candidates = {str(root), root.as_posix()}
        for candidate in sorted(candidates, key=len, reverse=True):
            if candidate:
                text = re.sub(
                    re.escape(candidate),
                    replacement,
                    text,
                    flags=re.IGNORECASE,
                )

    if settings is not None:
        for secret in (settings.llm_api_key, settings.asr_api_key, settings.app_password):
            if secret:
                text = text.replace(secret, "***")

    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text[:limit]


def redact_exception(
    exc: BaseException,
    settings: Settings | None = None,
    *,
    limit: int = 2000,
) -> str:
    """Redact an exception message before exposing it through logs or the API."""
    return redact_text(exc, settings, limit=limit)
