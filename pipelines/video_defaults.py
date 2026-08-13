"""Shared readers for runtime defaults in config/video_defaults.yaml.

This module is intentionally small: it centralizes video runtime defaults that
are not LLM routing. Provider/model/role routing remains in config/llm_router.yaml.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency in smoke tests
    yaml = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

HARD_FALLBACK_TTS_SPEED = 1.0
HARD_FALLBACK_WHISPER_LEAD_MS = 250
HARD_FALLBACK_SCENE_TAIL_PADDING_SEC = 1.2

_PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
_VIDEO_DEFAULTS_PATH = _PROJECT_ROOT / "config" / "video_defaults.yaml"
_MISSING = object()


def load_video_defaults() -> dict[str, Any]:
    """Load video_defaults.yaml as a dict, or return {} after warning."""
    if yaml is None:
        log.warning("Cannot load video_defaults.yaml: PyYAML unavailable; using hard fallbacks")
        return {}
    if not _VIDEO_DEFAULTS_PATH.exists():
        log.warning("Missing video_defaults.yaml at %s; using hard fallbacks", _VIDEO_DEFAULTS_PATH)
        return {}
    try:
        data = yaml.safe_load(_VIDEO_DEFAULTS_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        log.warning("Cannot parse video_defaults.yaml: %s; using hard fallbacks", exc)
        return {}
    if not isinstance(data, dict):
        log.warning("Invalid video_defaults.yaml root type %s; using hard fallbacks", type(data).__name__)
        return {}
    return data


def get_tts_speed() -> float:
    """Return tts.speed from config, with hard fallback."""
    return _get_float(("tts", "speed"), HARD_FALLBACK_TTS_SPEED)


def get_caption_whisper_lead_ms() -> int:
    """Return effective caption lead: env override > config > hard fallback."""
    env_raw = os.getenv("CAPTION_WHISPER_LEAD_MS")
    if env_raw is not None:
        try:
            return max(0, int(env_raw.strip()))
        except (TypeError, ValueError):
            log.warning(
                "Invalid CAPTION_WHISPER_LEAD_MS=%r; using hard fallback %d",
                env_raw,
                HARD_FALLBACK_WHISPER_LEAD_MS,
            )
            return HARD_FALLBACK_WHISPER_LEAD_MS
    return _get_int(("caption_timing", "whisper_lead_ms"), HARD_FALLBACK_WHISPER_LEAD_MS, minimum=0)


def get_scene_tail_padding_sec() -> float:
    """Return effective scene tail padding: env override > config > hard fallback."""
    env_raw = os.getenv("SCENE_TAIL_PADDING_SEC")
    if env_raw is not None:
        try:
            value = float(env_raw.strip())
            if value < 0:
                raise ValueError("negative padding")
            return value
        except (TypeError, ValueError):
            log.warning(
                "Invalid SCENE_TAIL_PADDING_SEC=%r; using hard fallback %.3f",
                env_raw,
                HARD_FALLBACK_SCENE_TAIL_PADDING_SEC,
            )
            return HARD_FALLBACK_SCENE_TAIL_PADDING_SEC
    return _get_float(("scene_render", "tail_padding_sec"), HARD_FALLBACK_SCENE_TAIL_PADDING_SEC, minimum=0.0)


def _get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def _label(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _get_float(path: tuple[str, ...], fallback: float, *, minimum: float | None = None) -> float:
    data = load_video_defaults()
    raw = _get_nested(data, path)
    if raw is _MISSING:
        log.warning("Missing video_defaults.yaml key %s; using hard fallback %.3f", _label(path), fallback)
        return fallback
    try:
        value = float(raw)
        if minimum is not None and value < minimum:
            raise ValueError(f"value below minimum {minimum}")
        return value
    except (TypeError, ValueError) as exc:
        log.warning(
            "Invalid video_defaults.yaml key %s=%r (%s); using hard fallback %.3f",
            _label(path),
            raw,
            exc,
            fallback,
        )
        return fallback


def _get_int(path: tuple[str, ...], fallback: int, *, minimum: int | None = None) -> int:
    data = load_video_defaults()
    raw = _get_nested(data, path)
    if raw is _MISSING:
        log.warning("Missing video_defaults.yaml key %s; using hard fallback %d", _label(path), fallback)
        return fallback
    try:
        value = int(raw)
        if minimum is not None and value < minimum:
            raise ValueError(f"value below minimum {minimum}")
        return value
    except (TypeError, ValueError) as exc:
        log.warning(
            "Invalid video_defaults.yaml key %s=%r (%s); using hard fallback %d",
            _label(path),
            raw,
            exc,
            fallback,
        )
        return fallback
