"""Central cost guard for external providers.

Defaults are intentionally conservative. Environment variables override
``config/video_defaults.yaml`` values at runtime.
"""
from __future__ import annotations

import os
from typing import Any

try:
    from video_defaults import load_video_defaults  # type: ignore[import]
except ImportError:
    from pipelines.video_defaults import load_video_defaults  # type: ignore[no-redef]


DEFAULT_POLICY: dict[str, bool] = {
    "allow_openai_api": False,
    "allow_claude_api": False,
    "allow_gemini_api": False,
    "allow_gemini_cli": True,
    "allow_codex_cli": True,
    "allow_ollama": False,
    "allow_azure_tts": True,
    "allow_openai_tts": False,
    "allow_whisper_api": False,
    # Local openai-whisper model execution (.venv, no external API call, no
    # per-request cost) — distinct from allow_whisper_api which gates a
    # hosted/paid Whisper API. Default-allowed since it's not a cost-guard
    # concern; see whisper_align.py.
    "allow_local_whisper": True,
    "allow_external_web": False,
}

ENV_OVERRIDES: dict[str, str] = {
    "allow_openai_api": "ALLOW_OPENAI_API",
    "allow_claude_api": "ALLOW_CLAUDE_API",
    "allow_gemini_api": "ALLOW_GEMINI_API",
    "allow_gemini_cli": "ALLOW_GEMINI_CLI",
    "allow_codex_cli": "ALLOW_CODEX_CLI",
    "allow_ollama": "ALLOW_OLLAMA",
    "allow_azure_tts": "ALLOW_AZURE_TTS",
    "allow_openai_tts": "ALLOW_OPENAI_TTS",
    "allow_whisper_api": "ALLOW_WHISPER_API",
    "allow_local_whisper": "ALLOW_LOCAL_WHISPER",
    "allow_external_web": "ALLOW_EXTERNAL_WEB",
}

PROVIDER_FLAGS: dict[str, str] = {
    "openai_api": "allow_openai_api",
    "claude_api": "allow_claude_api",
    "anthropic_api": "allow_claude_api",
    "gemini_api": "allow_gemini_api",
    "gemini_cli": "allow_gemini_cli",
    "codex_cli": "allow_codex_cli",
    "ollama": "allow_ollama",
    "azure_tts": "allow_azure_tts",
    "azure": "allow_azure_tts",
    "openai_tts": "allow_openai_tts",
    "openai": "allow_openai_tts",
    # Hosted/external Whisper API (not currently called anywhere in this
    # codebase) — kept conservative (default false) for future use.
    "whisper_api": "allow_whisper_api",
    "whisper": "allow_whisper_api",
    # Local .venv openai-whisper model load/inference — no external network
    # call, no per-request cost. Used by pipelines/whisper_align.py.
    "whisper_local": "allow_local_whisper",
    "gtts": "allow_external_web",
    "external_web": "allow_external_web",
}

class CostGuardBlocked(RuntimeError):
    """Raised when a provider is blocked by policy."""


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_config_policy() -> dict[str, bool]:
    data = load_video_defaults()
    raw_policy = data.get("cost_guard", {}) or {}
    return {
        key: bool(raw_policy[key])
        for key in DEFAULT_POLICY
        if key in raw_policy
    }


def get_policy() -> dict[str, bool]:
    policy = dict(DEFAULT_POLICY)
    policy.update(_load_config_policy())
    for key, env_name in ENV_OVERRIDES.items():
        if env_name in os.environ:
            policy[key] = _parse_bool(os.environ[env_name])
    return policy


def flag_for_provider(provider: str) -> str | None:
    return PROVIDER_FLAGS.get(provider)


def is_allowed(flag: str) -> bool:
    return bool(get_policy().get(flag, False))


def is_provider_allowed(provider: str) -> bool:
    flag = flag_for_provider(provider)
    if flag is None:
        return True
    return is_allowed(flag)


def blocked_reason(provider: str) -> str:
    flag = flag_for_provider(provider)
    if flag is None:
        return "no_cost_guard_flag"
    return f"{flag}=false"


def log_provider_usage(role: str, provider: str, allowed: bool) -> None:
    print(
        f"[PROVIDER_USAGE] role={role} provider={provider} allowed={str(allowed).lower()}",
        flush=True,
    )


def log_blocked(provider: str, role: str | None = None) -> None:
    role_part = f" role={role}" if role else ""
    print(
        f"[COST_GUARD_BLOCKED] provider={provider}{role_part} reason={blocked_reason(provider)}",
        flush=True,
    )


def ensure_provider_allowed(provider: str, role: str | None = None) -> None:
    allowed = is_provider_allowed(provider)
    log_provider_usage(role or "unknown", provider, allowed)
    if not allowed:
        log_blocked(provider, role)
        raise CostGuardBlocked(
            f"provider={provider} blocked by cost guard: {blocked_reason(provider)}"
        )
