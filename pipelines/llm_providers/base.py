"""Base protocol and result types for LLM providers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class ProviderStatus(str, Enum):
    OK = "ok"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXCEEDED = "quota_exceeded"
    AUTH_ERROR = "auth_error"
    MODEL_NOT_FOUND = "model_not_found"
    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    JSON_PARSE_FAIL = "json_parse_fail"
    EMPTY_OUTPUT = "empty_output"
    QUALITY_FAIL = "quality_check_fail"
    CLI_NOT_FOUND = "cli_not_found"
    NONZERO_EXIT = "nonzero_exit"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


# Per-provider approximate cost in KRW per 1K chars
_COST_TABLE: dict[str, float] = {
    "gemini_cli": 0.0,
    "codex_cli": 0.0,
    "claude_api_haiku": 2.5,
    "claude_api_sonnet": 12.0,
    "openai_api": 3.0,
    "ollama": 0.0,
}


@dataclass
class LLMResult:
    text: str
    provider: str
    role: str
    status: ProviderStatus = ProviderStatus.OK
    error_type: str | None = None
    model: str = ""
    input_chars: int = 0
    output_chars: int = 0
    estimated_cost_krw: float = 0.0
    duration_sec: float = 0.0
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @property
    def ok(self) -> bool:
        return self.status == ProviderStatus.OK

    def as_log_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "status": self.status.value,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
            "estimated_cost_krw": self.estimated_cost_krw,
            "duration_sec": round(self.duration_sec, 3),
            "error_type": self.error_type,
        }


def estimate_cost_krw(provider_key: str, output_chars: int) -> float:
    rate = _COST_TABLE.get(provider_key, 0.0)
    return round(rate * output_chars / 1000, 4)


@runtime_checkable
class LLMProvider(Protocol):
    """Interface every provider must implement."""

    @property
    def name(self) -> str: ...

    def available(self) -> bool:
        """Return True if the provider can be used right now."""
        ...

    def generate(
        self,
        prompt: str,
        *,
        role: str = "light",
        max_tokens: int = 4096,
        json_mode: bool = False,
        timeout_sec: int = 120,
        system: str | None = None,
    ) -> LLMResult:
        """Generate text. Always returns LLMResult; never raises."""
        ...
