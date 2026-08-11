"""Loads assets/theme.json and exposes design tokens."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_THEME_PATH = _PROJECT_ROOT / "assets" / "theme.json"

_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if not _THEME_PATH.exists():
        logger.error("theme.json not found at %s", _THEME_PATH)
        raise FileNotFoundError(f"theme.json missing: {_THEME_PATH}")
    _cache = json.loads(_THEME_PATH.read_text(encoding="utf-8"))
    logger.debug("Loaded theme tokens from %s", _THEME_PATH)
    return _cache


def get(key: str, default=None):
    return load().get(key, default)
