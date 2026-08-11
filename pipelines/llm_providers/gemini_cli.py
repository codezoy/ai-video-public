"""Gemini CLI provider — subprocess-based, unlimited quota.

Prompt delivery strategy (ISSUE-005-02 fix):
  - Short prompts (< _ARG_THRESHOLD chars): pass as positional argument
  - Long prompts or json_mode: pipe via stdin to avoid shell arg limits
    and reduce rate-limit surface from malformed arg escaping.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time

from .base import LLMResult, LLMProvider, ProviderStatus, estimate_cost_krw

try:
    from cost_guard import ensure_provider_allowed, CostGuardBlocked
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import ensure_provider_allowed, CostGuardBlocked  # type: ignore[no-redef]

log = logging.getLogger(__name__)

_DEFAULT_CLI = "/opt/homebrew/bin/gemini"
_DEFAULT_MODEL = "gemini-2.5-flash"

# Prompts longer than this are delivered via stdin instead of positional arg.
# Long args can trigger shell escaping issues and increase rate-limit surface.
_ARG_THRESHOLD = 2000

_AUTH_PATTERNS = ("auth", "unauthorized", "unauthenticated", "invalid credentials", "permission denied", "403")
_QUOTA_PATTERNS = ("quota", "resource_exhausted", "429", "too many requests")
_RATE_PATTERNS = ("rate", "rate limit", "rate_limit")


def _classify_cli_error(stderr: str) -> ProviderStatus:
    """Classify CLI failure from stderr into a specific ProviderStatus."""
    lower = stderr.lower()
    if any(p in lower for p in _AUTH_PATTERNS):
        return ProviderStatus.AUTH_ERROR
    if any(p in lower for p in _QUOTA_PATTERNS):
        return ProviderStatus.QUOTA_EXCEEDED
    if any(p in lower for p in _RATE_PATTERNS):
        return ProviderStatus.RATE_LIMIT
    return ProviderStatus.NONZERO_EXIT


class GeminiCLIProvider:
    """Calls `gemini` CLI via subprocess. Free tier — no API key needed."""

    name = "gemini_cli"

    def __init__(
        self,
        cli_path: str = _DEFAULT_CLI,
        model: str = _DEFAULT_MODEL,
        default_timeout: int = 120,
    ) -> None:
        self._cli = cli_path or os.environ.get("GEMINI_CLI_PATH", _DEFAULT_CLI)
        self._model = model
        self._timeout = default_timeout

    def available(self) -> bool:
        return os.path.isfile(self._cli) and os.access(self._cli, os.X_OK)

    def _run(
        self,
        full_prompt: str,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        """Execute gemini CLI. Uses stdin for long prompts, arg for short ones."""
        base_cmd = [self._cli, "--model", self._model]

        if len(full_prompt) <= _ARG_THRESHOLD:
            # Short prompt: pass as positional argument (original behaviour)
            return subprocess.run(
                base_cmd + [full_prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        # Long prompt: pipe via stdin to avoid escaping issues
        return subprocess.run(
            base_cmd + ["-p", "-"],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

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
                status=ProviderStatus.CLI_NOT_FOUND,
                error_type="cli_not_found",
            )

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        if json_mode:
            full_prompt = (
                "Respond with valid JSON only. No markdown fences, no prose.\n\n"
                + full_prompt
            )

        timeout = timeout_sec or self._timeout
        t0 = time.monotonic()

        try:
            result = self._run(full_prompt, timeout)
        except subprocess.TimeoutExpired:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.TIMEOUT,
                error_type="timeout",
                duration_sec=time.monotonic() - t0,
            )
        except Exception as exc:
            log.warning("gemini_cli subprocess error: %s", exc)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.ERROR,
                error_type=str(exc),
                duration_sec=time.monotonic() - t0,
            )

        duration = time.monotonic() - t0

        if result.returncode != 0:
            stderr = result.stderr.strip()
            log.warning("gemini_cli nonzero exit %d: %s", result.returncode, stderr[:200])
            status = _classify_cli_error(stderr)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=status,
                error_type=stderr[:200],
                duration_sec=duration,
            )

        text = result.stdout.strip()
        if not text:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.EMPTY_OUTPUT,
                error_type="empty_output",
                duration_sec=duration,
            )

        out_chars = len(text)
        return LLMResult(
            text=text,
            provider=self.name,
            role=role,
            status=ProviderStatus.OK,
            model=self._model,
            input_chars=len(full_prompt),
            output_chars=out_chars,
            estimated_cost_krw=estimate_cost_krw(self.name, out_chars),
            duration_sec=duration,
        )
