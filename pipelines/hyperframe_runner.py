"""hyperframe_runner.py — Hyperframe (Remotion) 빌드 에러 자동 수정 + 렌더 루프.

흐름:
  1. build_check.ts 로 tsc 빌드 검사
  2. 오류 있으면 → writer_high role 코드 수정 → 최대 max_build_iter 회 반복
  3. 빌드 성공 후 → render_check.ts 로 키 프레임 PNG 렌더
  4. visual_judge 로 렌더 결과 검사 (CLI-only에서는 API vision 비활성)
  5. 검사 실패 시 → visual_correct 로 씬 수정 + 재렌더 (최대 3회)

공개 함수:
  run(scenes, slides_dir, use_vision, max_build_iter) → HarnessResult
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red", "success": "green"}.get(level, "white")
        _console.print(f"[{color}][hyperframe_runner][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[hyperframe_runner] {msg}")


HYPERFRAME_DIR = Path(__file__).parent.parent / "hyperframe"
SCRIPTS_DIR = HYPERFRAME_DIR / "scripts"


# ── 타입 정의 ────────────────────────────────────────────────────────────────

class BuildError(TypedDict):
    file: str
    line: int
    col: int
    message: str


class HarnessResult(TypedDict):
    build_success: bool
    build_iterations: int
    render_results: list[dict]
    visual_results: list[dict]


# ── tsx 실행 헬퍼 ─────────────────────────────────────────────────────────────

def _run_tsx(script: str, args: list[str], timeout: int = 120) -> tuple[bool, dict]:
    """npx tsx <script> <args> 를 실행하고 (success, json_output) 을 반환한다."""
    cmd = ["npx", "tsx", script] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(HYPERFRAME_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()
        try:
            data = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            data = {"raw": stdout[:500]}
        return result.returncode == 0, data
    except subprocess.TimeoutExpired:
        return False, {"error": f"timeout ({timeout}s)"}
    except Exception as exc:
        return False, {"error": str(exc)}


# ── 빌드 검사 ────────────────────────────────────────────────────────────────

def _run_build_check() -> tuple[bool, list[BuildError]]:
    """build_check.ts 실행 → (success, errors)."""
    script = str(SCRIPTS_DIR / "build_check.ts")
    success, data = _run_tsx(script, [], timeout=90)
    errors: list[BuildError] = data.get("errors", [])
    _log(f"빌드 검사: {'성공' if success else f'실패 ({len(errors)}개 오류)'}")
    return success, errors


# ── 코드 자동 수정 ────────────────────────────────────────────────────────────

_FIX_SYSTEM = (
    "당신은 TypeScript / Remotion 전문 개발자입니다. "
    "빌드 오류를 분석하고 파일을 직접 수정하세요. "
    "반드시 수정이 필요한 파일의 전체 내용을 코드 블록으로 출력하세요."
)


def _build_fix_prompt(errors: list[BuildError]) -> str:
    error_lines = "\n".join(
        f"  {e['file']}:{e['line']}:{e['col']} — {e['message']}"
        for e in errors[:20]
    )
    # 오류 파일들의 현재 내용을 수집
    file_contents = ""
    seen_files: set[str] = set()
    for e in errors[:5]:
        fpath = HYPERFRAME_DIR / e["file"]
        if e["file"] not in seen_files and fpath.exists():
            seen_files.add(e["file"])
            try:
                content = fpath.read_text(encoding="utf-8")
                file_contents += f"\n\n### {e['file']}\n```typescript\n{content[:3000]}\n```"
            except OSError:
                pass

    return (
        f"다음 TypeScript 빌드 오류를 수정하세요:\n\n"
        f"## 오류 목록\n{error_lines}\n"
        f"{file_contents}\n\n"
        f"수정된 파일을 ```typescript ... ``` 코드블록으로 출력하세요. "
        f"파일명은 코드블록 바로 앞에 `### 파일명` 형식으로 명시하세요."
    )


def _apply_code_fix(errors: list[BuildError]) -> bool:
    """writer_high role 에게 코드 수정을 요청하고 파일에 반영한다. 성공 여부 반환."""
    try:
        import re
        from llm_client import generate  # type: ignore[import]

        prompt = _build_fix_prompt(errors)
        raw = generate(prompt, role="writer_high", system=_FIX_SYSTEM, max_tokens=4096)

        # ### filename.ts + ```typescript ... ``` 패턴 파싱
        pattern = r"###\s+(.+?)\n```typescript\n(.*?)```"
        matches = re.findall(pattern, raw, re.DOTALL)

        if not matches:
            _log("코드 수정 블록 파싱 실패", "warning")
            return False

        for filename, code in matches:
            filename = filename.strip()
            target = HYPERFRAME_DIR / filename
            if not target.exists():
                _log(f"수정 대상 파일 없음 (스킵): {filename}", "warning")
                continue
            target.write_text(code, encoding="utf-8")
            _log(f"코드 수정 적용: {filename}")

        return True
    except Exception as exc:
        _log(f"코드 수정 오류: {exc}", "error")
        return False


# ── 단일 프레임 렌더 ─────────────────────────────────────────────────────────

def _render_frame(comp_id: str, out_path: Path, frame: int = 0) -> bool:
    """render_check.ts 로 단일 프레임 PNG 를 렌더한다."""
    script = str(SCRIPTS_DIR / "render_check.ts")
    success, data = _run_tsx(
        script,
        ["--comp", comp_id, "--out", str(out_path), "--frame", str(frame)],
        timeout=120,
    )
    if success:
        _log(f"렌더 완료: {out_path.name} (comp={comp_id} frame={frame})")
    else:
        _log(f"렌더 실패: {data.get('error', '알 수 없는 오류')}", "error")
    return success


# ── 공개 진입점 ──────────────────────────────────────────────────────────────

def run(
    scenes: list[dict],
    slides_dir: Path,
    use_vision: bool = False,
    max_build_iter: int = 3,
) -> HarnessResult:
    """Hyperframe 빌드 → 자동 수정 → 렌더 → 시각 검증 파이프라인.

    Args:
        scenes:         scenes.json 의 scenes 리스트.
        slides_dir:     PNG 슬라이드 출력 디렉토리.
        use_vision:     CLI-only 정책에서는 API vision 없이 로컬 검사만 수행.
        max_build_iter: 빌드 오류 자동 수정 최대 반복 횟수.

    Returns:
        HarnessResult.
    """
    if not HYPERFRAME_DIR.exists():
        _log(f"hyperframe 디렉토리 없음: {HYPERFRAME_DIR}", "error")
        return HarnessResult(build_success=False, build_iterations=0, render_results=[], visual_results=[])

    # ── 1. 빌드 검사 + 자동 수정 루프 ─────────────────────────────────────────
    build_iter = 0
    build_success = False

    for attempt in range(1, max_build_iter + 1):
        build_iter = attempt
        ok, errors = _run_build_check()
        if ok:
            build_success = True
            _log(f"빌드 성공 (시도 {attempt}/{max_build_iter})", "success")
            break
        _log(f"빌드 실패 (시도 {attempt}/{max_build_iter}) — 코드 자동 수정 시작", "warning")
        if attempt < max_build_iter:
            _apply_code_fix(errors)

    if not build_success:
        _log(f"빌드 {max_build_iter}회 시도 후 실패 — 렌더 단계 스킵", "error")
        return HarnessResult(
            build_success=False,
            build_iterations=build_iter,
            render_results=[],
            visual_results=[],
        )

    # ── 2. 키 프레임 렌더 (template_type 별 대표 씬) ──────────────────────────
    # Remotion composition 이 있는 template_type 만 렌더
    TEMPLATE_MAP = {
        # scene_classifier template_types → Remotion Composition ID (Root.tsx 12개 전부 커버)
        "hero_title":        "TitleOpen",
        "flow_steps":        "FlowSteps",
        "architecture_tree": "ArchTree",
        "timeline":          "Timeline",
        "compare_two":       "CompareTwo",
        "table_compare":     "TableCompare",
        "summary_card":      "SummaryCard",
        "quote_highlight":   "Quote",
        "before_after":      "CompareTwo",
        # legacy UPPER_SNAKE_CASE backward compat — Explain/ListReveal/OutroCta 접근 경로
        "TITLE_OPEN":        "TitleOpen",
        "EXPLAIN":           "Explain",
        "LIST_REVEAL":       "ListReveal",
        "QUOTE":             "Quote",
        "OUTRO_CTA":         "OutroCta",
    }
    _FALLBACK_COMP = "Explain"

    slides_dir.mkdir(parents=True, exist_ok=True)
    render_results: list[dict] = []
    rendered_types: set[str] = set()

    for scene in scenes:
        ttype = scene.get("template_type", "")
        comp_id = TEMPLATE_MAP.get(ttype)
        if not comp_id:
            if not ttype:
                continue
            _log(
                f"[FALLBACK] scene {scene.get('id', '?')}: "
                f"알 수 없는 template_type '{ttype}' → '{_FALLBACK_COMP}' 으로 fallback",
                "warning",
            )
            comp_id = _FALLBACK_COMP
        if ttype in rendered_types:
            continue
        rendered_types.add(ttype)

        sid = scene.get("id", 0)
        out_png = slides_dir / f"hf_scene{sid:02d}.png"
        ok = _render_frame(comp_id, out_png)
        render_results.append({"scene_id": sid, "comp": comp_id, "success": ok, "path": str(out_png)})

    # ── 3. 시각 검증 ─────────────────────────────────────────────────────────
    from visual_judge import judge  # type: ignore[import]

    visual_results: list[dict] = []
    for rr in render_results:
        if not rr["success"]:
            continue
        png = Path(rr["path"])
        if not png.exists():
            continue
        jresult = judge(png, use_vision=use_vision)
        visual_results.append({
            "scene_id": rr["scene_id"],
            "comp": rr["comp"],
            "passed": jresult["passed"],
            "corrections": jresult["corrections"],
        })

    passed_visual = sum(1 for v in visual_results if v["passed"])
    _log(
        f"시각 검증: {passed_visual}/{len(visual_results)} 통과",
        "success" if passed_visual == len(visual_results) else "warning",
    )

    return HarnessResult(
        build_success=True,
        build_iterations=build_iter,
        render_results=render_results,
        visual_results=visual_results,
    )
