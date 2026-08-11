"""visual_correct.py — 슬라이드 자동 수정 루프 (최대 3회).

흐름:
  1. visual_judge 로 PNG 검사
  2. 실패 항목 → writer_high role 에 수정 지시 생성 요청
  3. render_animated_slide 로 슬라이드 재렌더
  4. 재검사 → 통과 or max_iter 도달 시 종료

공개 함수:
  correct_scene(scene, out_path, use_vision, max_iter) → CorrectionResult
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red", "success": "green"}.get(level, "white")
        _console.print(f"[{color}][visual_correct][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[visual_correct] {msg}")


# ── 타입 정의 ────────────────────────────────────────────────────────────────

class CorrectionResult(TypedDict):
    scene_id: int
    passed: bool
    iterations: int
    corrections_applied: list[str]


# ── 수정 지시 생성 ────────────────────────────────────────────────────────────

_CORRECT_SYSTEM = (
    "당신은 영상 슬라이드 자동 수정 시스템입니다. "
    "시각 검수 결과를 받아 슬라이드 데이터(JSON)를 수정하는 지시를 만듭니다. "
    "반드시 수정된 씬 JSON 만 출력하세요. 다른 설명은 필요 없습니다."
)


def _build_correct_prompt(scene: dict, corrections: list[str]) -> str:
    scene_json = json.dumps(scene, ensure_ascii=False, indent=2)
    corrections_text = "\n".join(f"- {c}" for c in corrections)
    return (
        f"다음 슬라이드 씬 JSON과 시각 검수에서 발견된 문제 목록이 있습니다.\n\n"
        f"## 현재 씬 JSON\n```json\n{scene_json}\n```\n\n"
        f"## 발견된 문제\n{corrections_text}\n\n"
        f"위 문제를 반영하여 수정된 씬 JSON을 출력하세요.\n"
        f"수정 가이드:\n"
        f"- 텍스트 잘림: narration/bullets 텍스트를 줄이거나 분리\n"
        f"- 색상 대비 부족: 텍스트 bullets 에 high_contrast 플래그 추가\n"
        f"- 강조 헤더 침범: emphasis 인덱스를 bullets 중간부로 이동\n"
        f"- 타이포 위계: title 을 짧게 하고 bullets 크기 조정\n\n"
        f"수정된 씬 JSON만 출력 (```json 코드블록 포함):"
    )


def _extract_json(raw: str) -> dict | None:
    """LLM 응답에서 JSON 블록을 추출한다."""
    # ```json ... ``` 블록 우선
    import re
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 중괄호 직접 탐색
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    return None


def _apply_correction(scene: dict, corrections: list[str]) -> dict:
    """writer_high role 에게 씬 JSON 수정을 요청하고 반환한다."""
    try:
        from llm_client import generate  # type: ignore[import]
        prompt = _build_correct_prompt(scene, corrections)
        raw = generate(prompt, role="writer_high", system=_CORRECT_SYSTEM, max_tokens=2048)
        corrected = _extract_json(raw)
        if corrected and isinstance(corrected, dict):
            _log(f"씬 {scene.get('id', '?')} 수정 JSON 적용")
            return corrected
        _log("수정 JSON 파싱 실패 — 원본 유지", "warning")
        return scene
    except Exception as exc:
        _log(f"수정 생성 오류: {exc}", "warning")
        return scene


# ── 슬라이드 재렌더 ──────────────────────────────────────────────────────────

def _rerender(scene: dict, out_path: Path) -> bool:
    """수정된 씬 데이터로 PNG 를 재생성한다."""
    try:
        import sys
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)

        from render_animated_slide import render_bullet_frame  # type: ignore[import]

        bullets = scene.get("bullets", [])
        normalized = [
            b if isinstance(b, dict)
            else {"text": b, "emphasis": [], "appear_at_ms": i * 3000}
            for i, b in enumerate(bullets)
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        render_bullet_frame(normalized, visible_until_idx=len(normalized) - 1, out_path=out_path)
        _log(f"재렌더 완료: {out_path.name}")
        return True
    except Exception as exc:
        _log(f"재렌더 실패: {exc}", "error")
        return False


# ── 공개 진입점 ──────────────────────────────────────────────────────────────

def correct_scene(
    scene: dict,
    out_path: Path,
    use_vision: bool = True,
    max_iter: int = 3,
) -> CorrectionResult:
    """씬 하나에 대해 자동 수정 루프를 실행한다.

    Args:
        scene:      씬 데이터 dict (id, bullets, narration 포함).
        out_path:   PNG 슬라이드 파일 경로.
        use_vision: CLI-only 정책에서는 API vision 없이 로컬 검사만 수행.
        max_iter:   최대 수정 반복 횟수 (기본 3).

    Returns:
        CorrectionResult — 최종 통과 여부 및 반복 횟수.
    """
    from visual_judge import judge  # type: ignore[import]

    scene_id = scene.get("id", 0)
    corrections_applied: list[str] = []
    current_scene = scene

    for iteration in range(1, max_iter + 1):
        _log(f"씬 {scene_id} 검사 (시도 {iteration}/{max_iter})")

        result = judge(out_path, use_vision=use_vision)
        if result["passed"]:
            _log(f"씬 {scene_id} 검사 통과 (시도 {iteration})", "success")
            return CorrectionResult(
                scene_id=scene_id,
                passed=True,
                iterations=iteration,
                corrections_applied=corrections_applied,
            )

        failed_corrections = result["corrections"]
        _log(f"씬 {scene_id} 실패: {failed_corrections}", "warning")
        corrections_applied.extend(failed_corrections)

        if iteration == max_iter:
            _log(f"씬 {scene_id} {max_iter}회 시도 후에도 실패 — 수동 검수 필요", "warning")
            break

        # 수정 지시 생성 + 재렌더
        current_scene = _apply_correction(current_scene, failed_corrections)
        if not _rerender(current_scene, out_path):
            _log(f"씬 {scene_id} 재렌더 실패 — 루프 중단", "error")
            break

    return CorrectionResult(
        scene_id=scene_id,
        passed=False,
        iterations=max_iter,
        corrections_applied=corrections_applied,
    )


def correct_all(
    scenes: list[dict],
    slides_dir: Path,
    use_vision: bool = True,
    max_iter: int = 3,
) -> list[CorrectionResult]:
    """scenes.json 내 모든 씬에 대해 correct_scene 을 실행한다."""
    results: list[CorrectionResult] = []
    for scene in scenes:
        sid = scene.get("id", 0)
        png_path = slides_dir / f"scene{sid:02d}.png"
        if not png_path.exists():
            _log(f"씬 {sid}: PNG 없음 ({png_path.name}) → 스킵", "warning")
            continue
        result = correct_scene(scene, png_path, use_vision=use_vision, max_iter=max_iter)
        results.append(result)

    passed = sum(1 for r in results if r["passed"])
    _log(f"전체 자동 수정 완료: {passed}/{len(results)} 통과")
    return results
