"""AI Motion Generator — Scene Plan → Motion Spec JSON.

흐름:
  scene_plan (dict | list)
  ↓
  codex_cli  (primary)
  ↓  실패 시
  gemini_cli (secondary)
  ↓  실패 시
  FAIL → sys.exit(1)

AI는 TSX/React 코드를 생성하지 않는다.
Motion Spec JSON만 출력한다.
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

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_WORK_DIR = _PROJECT_ROOT / "work"

# 허용 Primitive / Animation 목록 (motion_audit.py와 동기화)
ALLOWED_PRIMITIVES: list[str] = [
    "Hero", "Compare", "Highlight", "Timeline", "CodeBlock",
    "List", "Quote", "Stats", "Diagram", "Transition",
    "Summary",
]

ALLOWED_ANIMATIONS: list[str] = [
    "slide_in", "fade_in", "zoom_in", "wipe_left", "wipe_right",
    "bounce_in", "flip", "none",
]

ALLOWED_LAYOUTS: list[str] = [
    "full", "left_right", "top_bottom", "grid", "overlay", "centered",
]

ALLOWED_SCENE_TYPES: list[str] = [
    "intro", "concept", "compare", "timeline", "code", "list",
    "quote", "stats", "summary", "outro",
]

# ────────────────────────────────────────────────────────────────
# Motion Prompt
# ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
너는 15년차 모션그래픽 디자이너다.
TSX를 생성하지 마라. React Component를 생성하지 마라.
Motion Spec JSON만 생성하라.
Primitive Catalog 안에서만 장면을 구성하라.

허용 primitive_stack 값: Hero, Compare, Highlight, Timeline, CodeBlock, List, Quote, Stats, Diagram, Transition, Summary
허용 animation 값: slide_in, fade_in, zoom_in, wipe_left, wipe_right, bounce_in, flip, none
허용 layout 값: full, left_right, top_bottom, grid, overlay, centered
허용 scene_type 값: intro, concept, compare, timeline, code, list, quote, stats, summary, outro

출력 형식 — 반드시 JSON 배열:
[
  {
    "scene_id": "scene01",
    "title": "씬 핵심 제목",
    "scene_type": "concept",
    "layout": "full",
    "animation": "fade_in",
    "duration": 10,
    "emphasis": ["keyword1", "keyword2"],
    "primitive_stack": ["Hero", "Highlight"]
  },
  ...
]

규칙:
- title: 입력 Scene Plan의 title/heading을 그대로 사용하라 (4~15자 권장). scene_id("scene01" 등) 사용 금지.
- primitive_stack 길이: 1~5
- duration: 1~30 (초)
- emphasis: 0~5개 키워드
- JSON 이외 텍스트 금지 — 코드블록 없이 순수 JSON만 출력
"""


def _build_prompt(scene_plan: Any) -> str:
    plan_text = json.dumps(scene_plan, ensure_ascii=False, indent=2)
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"# Scene Plan\n\n{plan_text}\n\n"
        f"위 Scene Plan을 분석하고 Motion Spec JSON 배열을 생성하라."
    )


# ────────────────────────────────────────────────────────────────
# Provider Audit
# ────────────────────────────────────────────────────────────────

class _MotionProviderAudit:
    def __init__(self) -> None:
        self.attempts: list[dict] = []

    def record(self, provider: str, status: str, duration_sec: float, error: str | None = None) -> None:
        self.attempts.append({
            "provider": provider,
            "status": status,
            "duration_sec": round(duration_sec, 1),
            "error": error,
        })

    def emit(self, final_provider: str, pipeline_status: str) -> None:
        lines = ["[MOTION_PROVIDER_AUDIT]"]
        for i, a in enumerate(self.attempts, 1):
            lines.append(f"  attempt_{i}={a['provider']} status={a['status']} duration={a['duration_sec']}s")
            if a["error"]:
                lines.append(f"  error={a['error'][:80]}")
        lines.append(f"  final_provider={final_provider}")
        lines.append(f"  pipeline_status={pipeline_status}")
        print("\n".join(lines), flush=True)

        _write_motion_audit_log(self.attempts, final_provider, pipeline_status)


def _write_motion_audit_log(
    attempts: list[dict],
    final_provider: str,
    pipeline_status: str,
    work_dir: Path | None = None,
) -> None:
    _audit_dir = work_dir or Path(os.environ.get("WORK_DIR", str(_WORK_DIR)))
    audit_path = _audit_dir / "motion_provider_audit.json"
    try:
        _audit_dir.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        if audit_path.exists():
            try:
                existing = json.loads(audit_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "attempts": attempts,
            "final_provider": final_provider,
            "pipeline_status": pipeline_status,
        }
        existing.append(entry)
        audit_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("motion_provider_audit write failed: %s", exc)


# ────────────────────────────────────────────────────────────────
# JSON 추출
# ────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> list[dict] | None:
    text = text.strip()
    # 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

    # 배열 추출
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # 전체 파싱 시도
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    return None


# ────────────────────────────────────────────────────────────────
# LLM 호출
# ────────────────────────────────────────────────────────────────

def _call_router(prompt: str, provider: str) -> tuple[str, float]:
    """LLM Router를 통해 지정 provider로 호출. (text, duration_sec) 반환."""
    try:
        from llm_router import generate_with_router
    except ImportError:
        from pipelines.llm_router import generate_with_router  # type: ignore[no-redef]

    t0 = time.time()
    result = generate_with_router(
        prompt,
        role="motion_spec",
        json_mode=True,
        preferred_provider=provider,
        task_id="TASK_20260602_001",
    )
    duration = time.time() - t0
    return result.text, duration


# ────────────────────────────────────────────────────────────────
# Public Entry Point
# ────────────────────────────────────────────────────────────────

def generate_motion_spec(
    scene_plan: Any,
    output_path: Path | None = None,
    *,
    dry_run: bool = False,
) -> list[dict]:
    """scene_plan → Motion Spec JSON 배열 반환.

    실패 시 sys.exit(1).
    output_path 지정 시 JSON 파일로 저장.
    """
    prompt = _build_prompt(scene_plan)
    audit = _MotionProviderAudit()
    providers = ["codex_cli", "gemini_cli"]

    if dry_run:
        print("[MOTION_GEN] dry_run=true — skipping LLM call", flush=True)
        dummy = _make_dummy_spec(scene_plan)
        if output_path:
            _save(dummy, output_path)
        return dummy

    for provider in providers:
        print(f"[MOTION_GEN] provider={provider} attempting", flush=True)
        try:
            text, duration = _call_router(prompt, provider)
        except Exception as exc:
            audit.record(provider, "ERROR", 0.0, str(exc))
            log.warning("motion_gen provider=%s error: %s", provider, exc)
            continue

        specs = _extract_json(text)
        if specs is None:
            audit.record(provider, "JSON_FAIL", duration, "json_parse_fail")
            log.warning("motion_gen provider=%s json_parse_fail", provider)
            continue

        audit.record(provider, "OK", duration)
        audit.emit(provider, "PASS")
        log.info("[MOTION_GEN] provider=%s specs=%d duration=%.1fs", provider, len(specs), duration)
        print(f"[MOTION_GEN] provider={provider} specs={len(specs)} duration={duration:.1f}s status=PASS", flush=True)

        if output_path:
            _save(specs, output_path)
        return specs

    # 모든 provider 실패
    audit.emit("NONE", "FAIL")
    log.error("motion_gen all providers failed")
    print("[MOTION_GEN] status=FAIL all_providers_exhausted", flush=True)
    sys.exit(1)


def _save(specs: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(specs, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[MOTION_GEN] saved specs=%d path=%s", len(specs), path)
    print(f"[MOTION_GEN] saved path={path}", flush=True)


def _make_dummy_spec(scene_plan: Any) -> list[dict]:
    """dry_run용 더미 Motion Spec."""
    scenes = scene_plan if isinstance(scene_plan, list) else [scene_plan]
    return [
        {
            "scene_id": f"scene{i+1:02d}",
            "title": (
                s.get("title") or s.get("heading") or f"Scene {i+1}"
                if isinstance(s, dict) else f"Scene {i+1}"
            ),
            "scene_type": "concept",
            "layout": "full",
            "animation": "fade_in",
            "duration": 10,
            "emphasis": [],
            "primitive_stack": ["Hero"],
        }
        for i, s in enumerate(scenes[:3])
    ]


if __name__ == "__main__":
    import sys as _sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    sample_plan = [
        {"scene_id": "scene01", "title": "도입", "narration": "AI란 무엇인가?"},
        {"scene_id": "scene02", "title": "개념", "narration": "머신러닝과 딥러닝의 차이"},
        {"scene_id": "scene03", "title": "사례", "narration": "실제 적용 사례 3가지"},
    ]

    dry = "--dry-run" in _sys.argv
    specs = generate_motion_spec(sample_plan, dry_run=dry)
    print(json.dumps(specs, ensure_ascii=False, indent=2))
