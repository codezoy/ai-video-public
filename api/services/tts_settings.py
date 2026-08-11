"""Persist and resolve project-level TTS defaults."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SUPPORTED_TTS_PROVIDERS = frozenset({"azure", "chatterbox", "cosyvoice", "f5tts", "xtts"})
PRODUCTION_TTS_PROVIDERS = frozenset({"azure", "chatterbox"})
SYSTEM_FALLBACK_PROVIDER = os.getenv("TTS_DEFAULT_PROVIDER", "azure").strip().lower()
if SYSTEM_FALLBACK_PROVIDER not in SUPPORTED_TTS_PROVIDERS:
    SYSTEM_FALLBACK_PROVIDER = "azure"

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent.parent))
_SETTINGS_PATH = Path(os.getenv("AIVIDEO_SETTINGS_PATH", _PROJECT_ROOT / "data" / "settings.json"))


def load_tts_settings() -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    provider = str(data.get("default_provider") or "").strip().lower()
    if provider not in SUPPORTED_TTS_PROVIDERS:
        provider = SYSTEM_FALLBACK_PROVIDER
    voices = data.get("default_voices")
    if not isinstance(voices, dict):
        voices = {}
    return {
        "default_provider": provider,
        "default_voices": {
            key: value for key, value in voices.items()
            if key in SUPPORTED_TTS_PROVIDERS and isinstance(value, str) and value.strip()
        },
        "system_fallback_provider": SYSTEM_FALLBACK_PROVIDER,
    }


def save_tts_settings(default_provider: str, default_voices: dict[str, str]) -> dict[str, Any]:
    provider = default_provider.strip().lower()
    if provider not in SUPPORTED_TTS_PROVIDERS:
        raise ValueError(f"Unsupported TTS provider '{provider}'")
    payload = {
        "default_provider": provider,
        "default_voices": {
            key: value.strip() for key, value in default_voices.items()
            if key in SUPPORTED_TTS_PROVIDERS and isinstance(value, str) and value.strip()
        },
    }
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _SETTINGS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_SETTINGS_PATH)
    return load_tts_settings()


def resolve_tts(requested_provider: str | None, requested_voice: str | None) -> tuple[str, str | None]:
    settings = load_tts_settings()
    provider = (requested_provider or settings["default_provider"] or SYSTEM_FALLBACK_PROVIDER).strip().lower()
    if provider not in SUPPORTED_TTS_PROVIDERS:
        raise ValueError(f"Unsupported TTS provider '{provider}'")
    voice = requested_voice.strip() if requested_voice and requested_voice.strip() else None
    if voice is None:
        voice = settings["default_voices"].get(provider)
    return provider, voice
