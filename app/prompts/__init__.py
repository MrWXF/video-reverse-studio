"""Load versioned prompt templates and the shot-vocabulary catalog bundled with the app."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent
_CATALOG_PATH = _PROMPT_DIR / "catalog.json"
_CATALOG_CACHE: dict[tuple[str, int], dict] = {}


def load_prompt(name: str) -> str:
    """Read one bundled Markdown prompt template by name."""
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_catalog(override_path: str = "") -> dict:
    """Load the prompt vocabulary with mtime-based hot reload."""
    path = Path(override_path).expanduser() if override_path else _CATALOG_PATH
    if not path.is_absolute():
        path = (_PROMPT_DIR / path).resolve()
    try:
        mtime = path.stat().st_mtime_ns
        key = (str(path), mtime)
        if key in _CATALOG_CACHE:
            return _CATALOG_CACHE[key]
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "shot_types",
            "camera_moves",
            "lighting",
            "transitions",
            "palettes",
            "subjects",
            "scenes",
            "styles",
            "origins",
        }
        missing = required - set(payload)
        if missing:
            raise ValueError(f"prompt catalog missing keys: {sorted(missing)}")
        for key_name in required:
            if not payload[key_name]:
                raise ValueError(f"prompt catalog key is empty: {key_name}")
        _CATALOG_CACHE.clear()
        _CATALOG_CACHE[key] = payload
        return payload
    except Exception as exc:
        if path != _CATALOG_PATH:
            logger.warning("custom prompt catalog unavailable, using built-in: %s", exc)
            return load_catalog("")
        raise
