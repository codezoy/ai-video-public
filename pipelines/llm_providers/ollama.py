"""Ollama provider — local LLM, last_resort only."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from .base import LLMResult, ProviderStatus, estimate_cost_krw

log = logging.getLogger(__name__)

_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_WRITER = "qwen2.5:14b"
_DEFAULT_LIGHT = "gemma4:e4b"


class OllamaProvider:
    """Calls local Ollama via HTTP. Used only for last_resort roles."""

    name = "ollama"

    def __init__(
        self,
        host: str | None = None,
        writer_model: str | None = None,
        light_model: str | None = None,
        num_ctx: int = 16384,
        temperature: float = 0.5,
        top_p: float = 0.9,
        default_timeout: int = 300,
    ) -> None:
        self._host = (
            host
            or os.environ.get("OLLAMA_HOST", _DEFAULT_HOST)
        ).rstrip("/")
        self._writer_model = (
            writer_model or os.environ.get("OLLAMA_MODEL_WRITER", _DEFAULT_WRITER)
        )
        self._light_model = (
            light_model or os.environ.get("OLLAMA_MODEL_LIGHT", _DEFAULT_LIGHT)
        )
        self._num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", num_ctx))
        self._temperature = float(os.environ.get("OLLAMA_TEMPERATURE", temperature))
        self._top_p = float(os.environ.get("OLLAMA_TOP_P", top_p))
        self._timeout = default_timeout

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self._host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _pick_model(self, role: str) -> str:
        writer_roles = {"writer_high", "polisher", "regenerator"}
        return self._writer_model if role in writer_roles else self._light_model

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
                status=ProviderStatus.UNAVAILABLE,
                error_type="ollama_not_running",
            )

        model = self._pick_model(role)
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "num_ctx": self._num_ctx,
                "temperature": self._temperature,
                "top_p": self._top_p,
            },
        }
        if json_mode:
            payload["format"] = "json"

        body = json.dumps(payload).encode()
        url = f"{self._host}/api/generate"
        timeout = timeout_sec or self._timeout
        t0 = time.monotonic()

        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
        except TimeoutError:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.TIMEOUT,
                error_type="timeout",
                model=model,
                duration_sec=time.monotonic() - t0,
            )
        except Exception as exc:
            log.warning("ollama request error: %s", exc)
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.ERROR,
                error_type=str(exc)[:200],
                model=model,
                duration_sec=time.monotonic() - t0,
            )

        duration = time.monotonic() - t0

        try:
            data = json.loads(raw)
            text = data.get("response", "").strip()
        except json.JSONDecodeError:
            return LLMResult(
                text="",
                provider=self.name,
                role=role,
                status=ProviderStatus.INVALID_JSON,
                error_type="invalid_json_response",
                model=model,
                duration_sec=duration,
            )

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

        out_chars = len(text)
        return LLMResult(
            text=text,
            provider=self.name,
            role=role,
            status=ProviderStatus.OK,
            model=model,
            input_chars=len(full_prompt),
            output_chars=out_chars,
            estimated_cost_krw=estimate_cost_krw(self.name, out_chars),
            duration_sec=duration,
        )
