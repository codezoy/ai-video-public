"""Codex CLI provider — non-interactive subprocess via `codex exec`.

ISSUE-005-03 fix: use `codex exec` subcommand with --output-last-message
to capture the final agent response without requiring a TTY.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .base import LLMResult, LLMProvider, ProviderStatus, estimate_cost_krw

log = logging.getLogger(__name__)

_DEFAULT_CLI = "/opt/homebrew/bin/codex"

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


class CodexCLIProvider:
    """Calls `codex exec` non-interactively. Captures output via temp file."""

    name = "codex_cli"

    def __init__(
        self,
        cli_path: str = _DEFAULT_CLI,
        default_timeout: int = 120,
    ) -> None:
        self._cli = cli_path or os.environ.get("CODEX_CLI_PATH", _DEFAULT_CLI)
        self._timeout = default_timeout

    def available(self) -> bool:
        return os.path.isfile(self._cli) and os.access(self._cli, os.X_OK)

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

        # Write output to a temp file so we can read it cleanly after exec.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp_path = tmp.name

        cmd = [
            self._cli, "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--output-last-message", tmp_path,
            full_prompt,
        ]

        try:
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            _cleanup(tmp_path)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.TIMEOUT,
                error_type="timeout",
                duration_sec=time.monotonic() - t0,
            )
        except Exception as exc:
            _cleanup(tmp_path)
            log.warning("codex_cli subprocess error: %s", exc)
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
            log.warning("codex_cli nonzero exit %d: %s", result.returncode, stderr[:200])
            status = _classify_cli_error(stderr)
            _cleanup(tmp_path)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=status,
                error_type=stderr[:200],
                duration_sec=duration,
            )

        # Read from output file first; fall back to stdout if file is empty/missing
        text = _read_output(tmp_path) or result.stdout.strip()

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
            model="codex",
            input_chars=len(full_prompt),
            output_chars=out_chars,
            estimated_cost_krw=estimate_cost_krw(self.name, out_chars),
            duration_sec=duration,
        )


def _read_output(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
        return text
    except Exception:
        return ""
    finally:
        _cleanup(path)


def _cleanup(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
