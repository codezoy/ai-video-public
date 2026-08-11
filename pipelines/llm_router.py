"""LLM Provider Router — single entry point for all LLM calls.

Priority chain: gemini_cli → codex_cli.
Claude/OpenAI API and Ollama fallback stay blocked by CLI-only policy.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml  # PyYAML

from llm_providers import (
    LLMResult,
    ProviderStatus,
    GeminiCLIProvider,
    CodexCLIProvider,
    ClaudeAPIProvider,
    OpenAIAPIProvider,
    OllamaProvider,
)

try:
    from cost_guard import (
        get_policy,
        is_provider_allowed,
        log_blocked,
        log_provider_usage,
    )
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import (  # type: ignore[no-redef]
        get_policy,
        is_provider_allowed,
        log_blocked,
        log_provider_usage,
    )

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config" / "llm_router.yaml"
_LOG_DIR = _PROJECT_ROOT / "logs" / "llm_usage"
_AUDIT_LOG_PATH = _PROJECT_ROOT / "work" / "provider_audit.json"

_API_PROVIDERS = frozenset({"claude_api", "openai_api"})


class ProviderAuditLogger:
    """Records all provider attempts and emits a structured [PROVIDER_AUDIT] block."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.attempts: list[dict] = []

    def record(self, attempt_num: int, provider: str, result: LLMResult) -> None:
        lower_status = result.status.value
        classified = lower_status.upper()
        self.attempts.append({
            "attempt": attempt_num,
            "provider": provider,
            "result": classified,
            "duration_sec": round(result.duration_sec, 1),
            "error_type": result.error_type,
            "is_api_provider": provider in _API_PROVIDERS,
            "is_timeout": result.status == ProviderStatus.TIMEOUT,
            "is_auth_error": result.status == ProviderStatus.AUTH_ERROR,
            "is_quota_exceeded": result.status == ProviderStatus.QUOTA_EXCEEDED,
        })

    def emit(self, final_provider: str, pipeline_status: str) -> None:
        lines = ["[PROVIDER_AUDIT]"]
        for a in self.attempts:
            n = a["attempt"]
            lines.append(f"  attempt_{n}={a['provider']}")
            lines.append(f"  result={a['result']}")
            if a["duration_sec"]:
                lines.append(f"  duration={a['duration_sec']}s")
            if a["error_type"]:
                lines.append(f"  error_type={a['error_type'][:80]}")
        lines.append(f"  final_provider={final_provider}")
        lines.append(f"  pipeline_status={pipeline_status}")
        print("\n".join(lines), flush=True)
        self._write_audit_file(final_provider, pipeline_status)

    def _write_audit_file(self, final_provider: str, pipeline_status: str) -> None:
        try:
            _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            existing: list[dict] = []
            if _AUDIT_LOG_PATH.exists():
                try:
                    existing = json.loads(_AUDIT_LOG_PATH.read_text(encoding="utf-8"))
                except Exception:
                    existing = []
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "role": self.role,
                "provider_policy": {
                    "order": ["gemini_cli", "codex_cli"],
                    "forbidden": ["ollama", "claude_api", "openai_api"],
                },
                "attempts": self.attempts,
                "final_provider": final_provider,
                "api_fallback": any(a["is_api_provider"] for a in self.attempts if a["result"] == "OK"),
                "pipeline_status": pipeline_status,
                "api_fallback_occurred": any(a["is_api_provider"] for a in self.attempts if a["result"] == "OK"),
            }
            existing.append(entry)
            _AUDIT_LOG_PATH.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("provider_audit write failed: %s", exc)

# FAST_PATH role 판별 — 이 role에서 fast_path_timeout_sec 적용
_FAST_PATH_ROLES: frozenset[str] = frozenset({"fast_scene"})
# FAST_PATH timeout: FAST_LLM_CALL_TIMEOUT_SEC 환경변수 우선, 기본 300s (Codex 실 완료 시간 200-800s 범위 반영)
_FAST_TIMEOUT_SEC: int = int(os.getenv("FAST_LLM_CALL_TIMEOUT_SEC", "300"))
# Override: AIVIDEO_LLM_TIMEOUT_SEC takes highest priority when set
_AIVIDEO_TIMEOUT_OVERRIDE: int | None = (
    int(os.getenv("AIVIDEO_LLM_TIMEOUT_SEC"))
    if os.getenv("AIVIDEO_LLM_TIMEOUT_SEC")
    else None
)


def calc_dynamic_llm_timeout(target_scene_count: int, base_timeout: int = _FAST_TIMEOUT_SEC) -> int:
    """Compute a timeout (seconds) scaled to scene count.

    Priority:
    1. AIVIDEO_LLM_TIMEOUT_SEC env var (absolute override)
    2. dynamic: max(base_timeout, min(900, target_scene_count * 15))
    """
    if _AIVIDEO_TIMEOUT_OVERRIDE is not None:
        dynamic = _AIVIDEO_TIMEOUT_OVERRIDE
        source = "AIVIDEO_LLM_TIMEOUT_SEC"
    else:
        dynamic = max(base_timeout, min(900, target_scene_count * 15))
        source = "dynamic"
    print(
        f"[LLM_TIMEOUT]"
        f" target_scene_count={target_scene_count}"
        f" base_timeout={base_timeout}"
        f" dynamic_timeout={dynamic}"
        f" final_timeout={dynamic}"
        f" override_source={source}",
        flush=True,
    )
    return dynamic


# Fallback statuses that trigger switching to next provider
_FALLBACK_STATUSES = {
    ProviderStatus.RATE_LIMIT,
    ProviderStatus.QUOTA_EXCEEDED,
    ProviderStatus.AUTH_ERROR,
    ProviderStatus.MODEL_NOT_FOUND,
    ProviderStatus.TIMEOUT,
    ProviderStatus.INVALID_JSON,
    ProviderStatus.JSON_PARSE_FAIL,
    ProviderStatus.EMPTY_OUTPUT,
    ProviderStatus.QUALITY_FAIL,
    ProviderStatus.CLI_NOT_FOUND,
    ProviderStatus.NONZERO_EXIT,
    ProviderStatus.UNAVAILABLE,
    ProviderStatus.ERROR,
}


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Router config not found: {_CONFIG_PATH}")
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def _write_usage_log(result: LLMResult, task_id: str | None = None) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        date_str = time.strftime("%Y%m%d", time.gmtime())
        log_file = _LOG_DIR / f"{date_str}_{result.role}_{result.provider}.jsonl"
        entry = result.as_log_dict()
        if task_id:
            entry["task_id"] = task_id
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("usage log write failed: %s", exc)


class LLMRouter:
    """Routes LLM calls through the priority chain defined in llm_router.yaml."""

    def __init__(self) -> None:
        self._cfg = _load_config()
        self._providers = self._build_providers()
        self._role_cfg = self._cfg.get("roles", {})
        self._emit_cost_guard()

    def _emit_cost_guard(self) -> None:
        """파이프라인 시작 시 provider 정책을 stdout에 출력한다."""
        fast_cfg = self._role_cfg.get("fast_scene", {})
        order = fast_cfg.get("provider_order", ["gemini_cli", "codex_cli"])
        effective_order = [p for p in order if is_provider_allowed(p)]
        policy = get_policy()
        policy_summary = ",".join(
            f"{key}={str(value).lower()}" for key, value in sorted(policy.items())
        )
        forbidden = [p for p in ["ollama", "claude_api", "openai_api"] if not is_provider_allowed(p)]
        print(
            f"[COST_GUARD] {policy_summary}"
            f" provider_order={','.join(effective_order)}"
            f" fast_timeout_sec={_FAST_TIMEOUT_SEC}",
            flush=True,
        )
        print(
            f"[PROVIDER_POLICY] order={','.join(effective_order)}"
            f" forbidden={','.join(forbidden)}",
            flush=True,
        )

    def _build_providers(self) -> dict[str, Any]:
        pcfg = self._cfg.get("providers", {})

        gemini = GeminiCLIProvider(
            cli_path=pcfg.get("gemini_cli", {}).get("cli_path", "/opt/homebrew/bin/gemini"),
            model=pcfg.get("gemini_cli", {}).get("model", "gemini-2.5-flash"),
            default_timeout=pcfg.get("gemini_cli", {}).get("timeout_sec", 120),
        )
        codex = CodexCLIProvider(
            cli_path=pcfg.get("codex_cli", {}).get("cli_path", "/opt/homebrew/bin/codex"),
            default_timeout=pcfg.get("codex_cli", {}).get("timeout_sec", 120),
        )
        claude = ClaudeAPIProvider(
            default_timeout=pcfg.get("claude_api", {}).get("timeout_sec", 60),
        )
        openai = OpenAIAPIProvider(
            default_timeout=pcfg.get("openai_api", {}).get("timeout_sec", 60),
        )
        ollama = OllamaProvider(
            default_timeout=pcfg.get("ollama", {}).get("timeout_sec", 300),
        )

        return {
            "gemini_cli": gemini,
            "codex_cli": codex,
            "claude_api": claude,
            "openai_api": openai,
            "ollama": ollama,
        }

    def _get_provider_chain(self, role: str) -> list[Any]:
        rcfg = self._role_cfg.get(role, {})
        order = rcfg.get("provider_order", ["gemini_cli", "codex_cli"])
        last_resort = rcfg.get("last_resort", False)
        pcfg = self._cfg.get("providers", {})

        chain = []
        for name in order:
            if not pcfg.get(name, {}).get("enabled", True):
                log.debug("Provider %s disabled in llm_router.yaml, skipping", name)
                continue
            if not is_provider_allowed(name):
                log_blocked(name, role)
                continue
            p = self._providers.get(name)
            if p is not None and name != "ollama":
                chain.append(p)

        # Append ollama only if last_resort is true for this role
        if last_resort and is_provider_allowed("ollama"):
            chain.append(self._providers["ollama"])

        return chain

    def _quality_ok(self, text: str, role: str, json_mode: bool = False) -> bool:
        stripped = text.strip()
        if not stripped:
            return False

        rcfg = self._role_cfg.get(role, {})

        # JSON mode: validate structure, not char count.
        # A short valid JSON array (e.g. ["a","b"]) must pass.
        use_json_check = json_mode or rcfg.get("json_quality_check", False)
        if use_json_check:
            try:
                json.loads(stripped)
                return True
            except json.JSONDecodeError:
                m = re.search(r"[\[{].*[\]}]", stripped, re.DOTALL)
                if m:
                    try:
                        json.loads(m.group())
                        return True
                    except json.JSONDecodeError:
                        pass
            return False

        min_chars = rcfg.get("quality_min", 0)
        return len(stripped) >= min_chars

    def generate(
        self,
        prompt: str,
        role: str = "light",
        *,
        max_tokens: int = 4096,
        json_mode: bool = False,
        timeout_sec: int | None = None,
        system: str | None = None,
        preferred_provider: str | None = None,
        task_id: str | None = None,
    ) -> LLMResult:
        """Try providers in priority order. Returns first successful result."""
        chain = self._get_provider_chain(role)
        prompt_chars = len(prompt)

        if not chain:
            log.error("No providers configured for role '%s'", role)
            return LLMResult(
                text="",
                provider="none",
                role=role,
                status=ProviderStatus.UNAVAILABLE,
                error_type="no_providers_configured",
            )

        # Move preferred provider to front if specified
        if preferred_provider:
            chain_names = [p.name for p in chain]
            if preferred_provider in chain_names:
                idx = chain_names.index(preferred_provider)
                chain = [chain[idx]] + chain[:idx] + chain[idx + 1:]

        rcfg = self._role_cfg.get(role, {})
        use_high_tier = rcfg.get("claude_tier") == "high"

        # Explicit caller timeout wins. FAST_PATH env override wins over role config.
        effective_timeout = timeout_sec
        if role in _FAST_PATH_ROLES and effective_timeout is None:
            effective_timeout = _FAST_TIMEOUT_SEC
        if effective_timeout is None:
            effective_timeout = rcfg.get("timeout_sec")

        chain_len = len(chain)
        last_result: LLMResult | None = None
        fallback_count = 0
        prev_provider: str | None = None
        audit = ProviderAuditLogger(role)
        attempt_num = 0

        for attempt_idx, provider in enumerate(chain):
            if not provider.available():
                log.debug("Provider %s unavailable for role %s, skipping", provider.name, role)
                continue

            if prev_provider is not None:
                # Explicit [LLM_FALLBACK] stdout log — not silent
                print(
                    f"[LLM_FALLBACK] role={role} from={prev_provider} to={provider.name}"
                    f" reason={last_result.status.value if last_result else 'unavailable'}",
                    flush=True,
                )
                fallback_count += 1

            attempt_num += 1
            print(
                f"[PROVIDER_ATTEMPT] role={role} provider={provider.name}"
                f" attempt={attempt_num}",
                flush=True,
            )
            log_provider_usage(role, provider.name, True)
            log.debug("Trying provider %s for role %s", provider.name, role)

            # Claude gets special high-tier flag
            if provider.name == "claude_api":
                result = provider.generate(
                    prompt,
                    role=role,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    timeout_sec=effective_timeout,
                    system=system,
                    use_high_tier=use_high_tier,
                )
            else:
                result = provider.generate(
                    prompt,
                    role=role,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    timeout_sec=effective_timeout,
                    system=system,
                )

            print(
                f"[PROVIDER_RESULT] role={role} provider={provider.name}"
                f" status={result.status.value} elapsed_ms={int(result.duration_sec * 1000)}"
                f" prompt_chars={prompt_chars} timeout_sec={effective_timeout}",
                flush=True,
            )
            _write_usage_log(result, task_id=task_id)
            last_result = result
            audit.record(attempt_num, provider.name, result)

            if result.status == ProviderStatus.TIMEOUT:
                print(
                    f"[LLM_TIMEOUT] role={role} provider={provider.name}"
                    f" limit_sec={effective_timeout} elapsed_sec={result.duration_sec:.0f}",
                    flush=True,
                )

            if result.status not in _FALLBACK_STATUSES:
                if not self._quality_ok(result.text, role, json_mode=json_mode):
                    log.warning(
                        "Provider %s output too short (%d chars) for role %s, trying next",
                        provider.name,
                        len(result.text),
                        role,
                    )
                    result.status = ProviderStatus.QUALITY_FAIL
                    prev_provider = provider.name
                    continue
                log.info(
                    "role=%s provider=%s status=ok chars=%d cost=%.4f KRW dur=%.1fs",
                    role,
                    result.provider,
                    result.output_chars,
                    result.estimated_cost_krw,
                    result.duration_sec,
                )
                print(
                    f"[LLM_PROFILE] role={role} provider={result.provider}"
                    f" duration_sec={result.duration_sec:.1f} retry=0 fallback={fallback_count}"
                    f" prompt_chars={prompt_chars} output_chars={result.output_chars} status=PASS",
                    flush=True,
                )
                audit.emit(provider.name, "PASS")
                return result

            log.warning(
                "Provider %s failed for role %s: %s — trying next",
                provider.name,
                role,
                result.status.value,
            )
            prev_provider = provider.name

        # All providers exhausted
        if last_result is not None:
            log.error("All providers exhausted for role '%s'", role)
            print(
                f"[LLM_PROFILE] role={role} provider={last_result.provider}"
                f" duration_sec={last_result.duration_sec:.1f} retry=0 fallback={fallback_count}"
                f" prompt_chars={prompt_chars} output_chars={last_result.output_chars} status=FAIL",
                flush=True,
            )
            audit.emit("NONE", "FAIL")
            return last_result

        audit.emit("NONE", "FAIL")
        return LLMResult(
            text="",
            provider="none",
            role=role,
            status=ProviderStatus.UNAVAILABLE,
            error_type="all_providers_failed",
        )

    def show_routing(self) -> None:
        """Print routing table for dry-run verification."""
        print("\n=== LLM Router — Provider Priority Table ===\n")
        for role, rcfg in self._role_cfg.items():
            chain = self._get_provider_chain(role)
            available = [p.name for p in chain if p.available()]
            skipped = [p.name for p in chain if not p.available()]
            last_resort = rcfg.get("last_resort", False)
            print(
                f"  {role:<25} chain={[p.name for p in chain]}"
                f"  available={available}"
                f"  skipped={skipped}"
                f"  last_resort={last_resort}"
            )
        print()


# Module-level singleton (lazy)
_router: LLMRouter | None = None


def _get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def generate_with_router(
    prompt: str,
    role: str = "light",
    *,
    max_tokens: int = 4096,
    json_mode: bool = False,
    timeout_sec: int | None = None,
    system: str | None = None,
    preferred_provider: str | None = None,
    task_id: str | None = None,
) -> LLMResult:
    """Public entry point. Returns LLMResult; never raises."""
    return _get_router().generate(
        prompt,
        role,
        max_tokens=max_tokens,
        json_mode=json_mode,
        timeout_sec=timeout_sec,
        system=system,
        preferred_provider=preferred_provider,
        task_id=task_id,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if "--dry-run" in sys.argv:
        _get_router().show_routing()
        sys.exit(0)

    # Quick smoke test
    result = generate_with_router("ping", role="light")
    print(f"status={result.status.value} provider={result.provider} chars={result.output_chars}")
