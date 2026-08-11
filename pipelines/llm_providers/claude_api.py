"""Claude API provider — wraps existing anthropic SDK calls."""
from __future__ import annotations

import logging
import os
import time

from .base import LLMResult, ProviderStatus, estimate_cost_krw

try:
    from cost_guard import ensure_provider_allowed, CostGuardBlocked
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import ensure_provider_allowed, CostGuardBlocked  # type: ignore[no-redef]

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_HIGH_MODEL = "claude-sonnet-4-6"


class ClaudeAPIProvider:
    """Calls Anthropic Claude via the anthropic SDK."""

    name = "claude_api"

    def __init__(
        self,
        default_model: str = _DEFAULT_MODEL,
        high_model: str = _HIGH_MODEL,
        default_timeout: int = 60,
    ) -> None:
        self._default_model = os.environ.get("CLAUDE_HAIKU_MODEL", default_model)
        self._high_model = os.environ.get("CLAUDE_MODEL", high_model)
        self._timeout = default_timeout
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic  # type: ignore
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    return None
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                log.warning("anthropic package not installed")
                return None
        return self._client

    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def generate(
        self,
        prompt: str,
        *,
        role: str = "light",
        max_tokens: int = 4096,
        json_mode: bool = False,
        timeout_sec: int | None = None,
        system: str | None = None,
        use_high_tier: bool = False,
    ) -> LLMResult:
        model = self._high_model if use_high_tier else self._default_model
        try:
            ensure_provider_allowed(self.name, role)
        except CostGuardBlocked:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.UNAVAILABLE,
                error_type="cost_guard_blocked",
                model=model,
            )

        if not self.available():
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.UNAVAILABLE,
                error_type="no_api_key",
            )

        client = self._get_client()
        if client is None:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.UNAVAILABLE,
                error_type="client_init_failed",
            )

        messages = [{"role": "user", "content": prompt}]
        if json_mode:
            messages[0]["content"] = (
                "Respond with valid JSON only. No markdown fences, no prose.\n\n" + prompt
            )

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        t0 = time.monotonic()
        try:
            print(
                f"[CLAUDE_USAGE] caller={__file__}"
                f" function=ClaudeAPIProvider.generate role={role} model={model}",
                flush=True,
            )
            response = client.messages.create(**kwargs)
        except Exception as exc:
            duration = time.monotonic() - t0
            err = str(exc).lower()
            if "rate" in err or "429" in err:
                status = ProviderStatus.RATE_LIMIT
            elif "quota" in err or "billing" in err:
                status = ProviderStatus.QUOTA_EXCEEDED
            elif "timeout" in err:
                status = ProviderStatus.TIMEOUT
            else:
                status = ProviderStatus.ERROR
            log.warning("claude_api error [%s]: %s", status.value, exc)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=status,
                error_type=str(exc)[:200],
                model=model,
                duration_sec=duration,
            )

        duration = time.monotonic() - t0
        text = response.content[0].text.strip() if response.content else ""
        if not text:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.EMPTY_OUTPUT,
                error_type="empty_output",
                model=model,
                duration_sec=duration,
            )

        cost_key = "claude_api_sonnet" if use_high_tier else "claude_api_haiku"
        out_chars = len(text)
        return LLMResult(
            text=text,
            provider=self.name,
            role=role,
            status=ProviderStatus.OK,
            model=model,
            input_chars=len(prompt),
            output_chars=out_chars,
            estimated_cost_krw=estimate_cost_krw(cost_key, out_chars),
            duration_sec=duration,
        )
