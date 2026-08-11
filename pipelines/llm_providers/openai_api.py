"""OpenAI API provider — fallback when free CLIs and Claude are exhausted."""
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

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIAPIProvider:
    """Calls OpenAI via the openai SDK."""

    name = "openai_api"

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        default_timeout: int = 60,
    ) -> None:
        self._model = os.environ.get("OPENAI_ROUTER_MODEL", model)
        self._timeout = default_timeout
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is None:
            try:
                import openai  # type: ignore
                api_key = os.environ.get("OPENAI_API_KEY", "")
                if not api_key:
                    return None
                self._client = openai.OpenAI(api_key=api_key)
            except ImportError:
                log.warning("openai package not installed")
                return None
        return self._client

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())

    def generate(
        self,
        prompt: str,
        *,
        role: str = "light",
        max_tokens: int = 4096,
        json_mode: bool = False,
        timeout_sec: int | None = None,
        system: str | None = None,
    ) -> LLMResult:
        try:
            ensure_provider_allowed(self.name, role)
        except CostGuardBlocked:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.UNAVAILABLE,
                error_type="cost_guard_blocked",
                model=self._model,
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

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
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
            log.warning("openai_api error [%s]: %s", status.value, exc)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=status,
                error_type=str(exc)[:200],
                model=self._model,
                duration_sec=duration,
            )

        duration = time.monotonic() - t0
        choice = response.choices[0] if response.choices else None
        text = choice.message.content.strip() if choice and choice.message.content else ""

        if not text:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.EMPTY_OUTPUT,
                error_type="empty_output",
                model=self._model,
                duration_sec=duration,
            )

        out_chars = len(text)
        return LLMResult(
            text=text,
            provider=self.name,
            role=role,
            status=ProviderStatus.OK,
            model=self._model,
            input_chars=len(prompt),
            output_chars=out_chars,
            estimated_cost_krw=estimate_cost_krw(self.name, out_chars),
            duration_sec=duration,
        )
