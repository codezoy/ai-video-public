"""LLM Router — generate() 단일 진입점. 내부적으로 llm_router.py 에 위임한다.

기존 호출부 호환성을 위해 generate(prompt, role) → str 시그니처를 유지한다.
실제 라우팅 로직은 pipelines/llm_router.py 의 generate_with_router() 가 담당한다.
CLI-only 정책에서는 라우터 실패 시 레거시 Claude/Ollama 경로로 폴백하지 않는다.
vision 호출의 Claude API 직접 경로도 비활성화한다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][llm_client][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[llm_client] {msg}")

# ── 환경변수 (레거시 호환) ────────────────────────────────────────────────────
BACKEND: str       = os.getenv("LLM_BACKEND", "ollama")
POLISH: str        = os.getenv("LLM_POLISH", "claude-haiku")
_raw_ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_HOST: str = _raw_ollama_host if _raw_ollama_host.startswith("http") else f"http://{_raw_ollama_host}"
M_LIGHT: str       = os.getenv("OLLAMA_MODEL_LIGHT", "gemma4:e4b")
CLAUDE_MODEL: str       = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_HAIKU: str       = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
LLM_JUDGE: str          = os.getenv("LLM_JUDGE", "claude-sonnet-4-6")
WRITER_HIGH: str        = os.getenv("LLM_WRITER_HIGH", "claude-sonnet-4-6")
OLLAMA_NUM_CTX: int     = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.5"))
OLLAMA_TOP_P: float     = float(os.getenv("OLLAMA_TOP_P", "0.9"))

_BACKOFF_SECONDS = (0,)  # 레거시 경로 재시도 제거 — 1회만 시도 (wait=0)

# ── llm_router 로드 (실패 시 레거시 경로로 폴백) ─────────────────────────────
_PIPELINES_DIR = Path(__file__).parent
if str(_PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINES_DIR))

try:
    from llm_router import generate_with_router as _router_generate  # type: ignore[import]
    from llm_providers import ProviderStatus  # type: ignore[import]
    _ROUTER_AVAILABLE = True
except Exception as _e:
    _log(f"llm_router 로드 실패, 레거시 경로 사용: {_e}", "warning")
    _ROUTER_AVAILABLE = False

try:
    from cost_guard import ensure_provider_allowed
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import ensure_provider_allowed  # type: ignore[no-redef]


# ── 레거시 모델 선택 (CLI-only 정책에서 비활성) ───────────────────────────────
def _pick(role: Literal["fast_scene", "writer_high", "polisher", "light", "judge", "vision_judge", "summarizer", "topic_guard"]) -> str:
    """Legacy direct model selector is disabled; use llm_router provider_order."""
    raise RuntimeError(
        f"[PROVIDER_GUARD] legacy model selection disabled for role={role}; "
        "use llm_router CLI providers."
    )


# ── 레거시 직접 호출 차단 ────────────────────────────────────────────────────
def _call_ollama(model: str, system: str, prompt: str, **kw: object) -> str:
    raise RuntimeError(
        "[PROVIDER_GUARD] direct Ollama fallback is disabled by CLI-only policy."
    )


def _call_claude(model: str, system: str, prompt: str, **kw: object) -> str:
    ensure_provider_allowed("claude_api", str(kw.get("role", "legacy_llm")))
    raise RuntimeError(
        "[PROVIDER_GUARD] direct Claude API fallback is disabled by CLI-only policy."
    )


def _call_claude_vision(model: str, system: str, prompt: str, image_path: str, **kw: object) -> str:
    """Legacy API vision path is disabled by CLI-only policy."""
    ensure_provider_allowed("claude_api", "vision_judge")
    raise RuntimeError(
        "[PROVIDER_GUARD] direct Claude vision API is disabled by CLI-only policy."
    )


# ── 공개 진입점 ───────────────────────────────────────────────────────────────
def generate(
    prompt: str,
    role: Literal["fast_scene", "writer_high", "polisher", "light", "judge", "vision_judge", "summarizer", "topic_guard"],
    system: str = "",
    **kw: object,
) -> str:
    """LLM Router 단일 진입점.

    llm_router 사용 가능 시 → generate_with_router() 위임 (우선순위 체인)
    llm_router 불가 시      → 레거시 _pick() + _call_* 경로 (3회 백오프)
    """
    if _ROUTER_AVAILABLE:
        result = _router_generate(
            prompt,
            role=role,
            max_tokens=int(kw.get("max_tokens", 4096)),
            system=system or None,
            timeout_sec=int(kw["timeout_sec"]) if "timeout_sec" in kw else None,
        )
        if result.status == ProviderStatus.OK:
            _log(f"role={role} → provider={result.provider} model={result.model} chars={result.output_chars}")
            return result.text
        # [PROVIDER_GUARD] Router is available but all providers exhausted.
        # Do NOT fall back to legacy path — that could silently use a blocked API.
        print(
            f"[PROVIDER_GUARD] role={role} all_providers_exhausted"
            f" last_status={result.status.value} last_provider={result.provider}"
            f" api_fallback=BLOCKED",
            flush=True,
        )
        raise RuntimeError(
            f"[PROVIDER_GUARD] All providers exhausted for role={role}."
            f" last_status={result.status.value} provider={result.provider}."
            " Claude/OpenAI API fallback is blocked by cost guard."
        )

    raise RuntimeError(
        "[PROVIDER_GUARD] llm_router unavailable. "
        "Legacy Claude/Ollama fallback is disabled by CLI-only policy."
    )


def generate_vision(
    prompt: str,
    image_path: str,
    system: str = "",
    **kw: object,
) -> str:
    """vision_judge 전용 진입점 — CLI-only 정책에서는 API vision을 사용하지 않는다."""
    raise RuntimeError(
        "[PROVIDER_GUARD] vision_judge API vision is disabled by CLI-only policy. "
        "Use local/PIL visual checks instead."
    )


def show_routing() -> None:
    """dry-run 용 — 현재 .env 기준 라우팅 결과를 출력한다."""
    if _ROUTER_AVAILABLE:
        from llm_router import _get_router  # type: ignore[import]
        _get_router().show_routing()
    else:
        for role in ("fast_scene", "writer_high", "polisher", "light", "judge", "vision_judge"):
            try:
                model = _pick(role)  # type: ignore[arg-type]
            except EnvironmentError as e:
                model = f"[ERROR] {e}"
            _log(f"role={role:12s} → {model}", "info")


# ── CLI ───────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llm_client.py",
        description="LLM Router — 현재 .env 기준 라우팅 결과를 확인하거나 간단한 생성 테스트를 수행한다.",
    )
    p.add_argument("--show-routing", action="store_true", help="role → 모델 매핑만 출력하고 종료")
    p.add_argument("--role", choices=["fast_scene", "writer_high", "polisher", "light"], default="fast_scene")
    p.add_argument("--prompt", default="안녕하세요, 테스트입니다.")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.show_routing:
        show_routing()
        return
    result = generate(args.prompt, role=args.role)  # type: ignore[arg-type]
    print(result)


if __name__ == "__main__":
    main()
