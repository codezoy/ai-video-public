"""Motion Audit — Motion Spec JSON 유효성 검사.

MVP 검사 항목 (9개):
  1. scene_type 존재
  2. primitive_stack 존재
  3. primitive_stack 길이 1~5
  4. duration 1~30
  5. layout 존재
  6. animation 존재
  7. 허용 primitive만 사용
  8. 허용 animation만 사용
  9. JSON schema 유효 (필수 필드 존재)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# 허용 목록 (ai_motion_generator.py와 동기화)
# ────────────────────────────────────────────────────────────────

ALLOWED_PRIMITIVES: frozenset[str] = frozenset({
    "Hero", "Compare", "Highlight", "Timeline", "CodeBlock",
    "List", "Quote", "Stats", "Diagram", "Transition",
    "Summary",  # added: MVP Primitive Renderer support
})

ALLOWED_ANIMATIONS: frozenset[str] = frozenset({
    "slide_in", "fade_in", "zoom_in", "wipe_left", "wipe_right",
    "bounce_in", "flip", "none",
})

ALLOWED_LAYOUTS: frozenset[str] = frozenset({
    "full", "left_right", "top_bottom", "grid", "overlay", "centered",
})

ALLOWED_SCENE_TYPES: frozenset[str] = frozenset({
    "intro", "concept", "compare", "timeline", "code", "list",
    "quote", "stats", "summary", "outro",
})

REQUIRED_FIELDS: tuple[str, ...] = (
    "scene_id", "scene_type", "layout", "animation", "duration", "primitive_stack",
)


# ────────────────────────────────────────────────────────────────
# Result Types
# ────────────────────────────────────────────────────────────────

@dataclass
class SceneAuditResult:
    scene_id: str
    passed: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "passed": self.passed,
            "violations": self.violations,
        }


@dataclass
class MotionAuditReport:
    passed: bool
    total_scenes: int
    passed_scenes: int
    failed_scenes: int
    scene_results: list[SceneAuditResult] = field(default_factory=list)
    global_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_scenes": self.total_scenes,
            "passed_scenes": self.passed_scenes,
            "failed_scenes": self.failed_scenes,
            "scene_results": [r.to_dict() for r in self.scene_results],
            "global_errors": self.global_errors,
        }

    def print_summary(self) -> None:
        status = "PASS" if self.passed else "FAIL"
        print(
            f"[MOTION_AUDIT] status={status}"
            f" total={self.total_scenes}"
            f" passed={self.passed_scenes}"
            f" failed={self.failed_scenes}",
            flush=True,
        )
        for r in self.scene_results:
            if not r.passed:
                print(f"[MOTION_AUDIT] scene={r.scene_id} violations={r.violations}", flush=True)
        for err in self.global_errors:
            print(f"[MOTION_AUDIT] global_error={err}", flush=True)


# ────────────────────────────────────────────────────────────────
# Per-scene 검사
# ────────────────────────────────────────────────────────────────

def _audit_scene(scene: Any, index: int) -> SceneAuditResult:
    scene_id = scene.get("scene_id", f"scene_{index:02d}") if isinstance(scene, dict) else f"scene_{index:02d}"
    violations: list[str] = []

    if not isinstance(scene, dict):
        return SceneAuditResult(scene_id=scene_id, passed=False, violations=["not_a_dict"])

    # [9] JSON schema — 필수 필드 존재 여부
    for req in REQUIRED_FIELDS:
        if req not in scene:
            violations.append(f"missing_field:{req}")

    if violations:
        return SceneAuditResult(scene_id=scene_id, passed=False, violations=violations)

    # [1] scene_type 존재 + 허용값
    scene_type = scene.get("scene_type", "")
    if not scene_type:
        violations.append("scene_type:empty")
    elif scene_type not in ALLOWED_SCENE_TYPES:
        violations.append(f"scene_type:invalid:{scene_type}")

    # [2] primitive_stack 존재
    pstack = scene.get("primitive_stack")
    if not pstack:
        violations.append("primitive_stack:empty")
    elif not isinstance(pstack, list):
        violations.append("primitive_stack:not_a_list")
    else:
        # [3] 길이 1~5
        if not (1 <= len(pstack) <= 5):
            violations.append(f"primitive_stack:length:{len(pstack)} (allowed 1-5)")
        # [7] 허용 primitive만
        invalid_prims = [p for p in pstack if p not in ALLOWED_PRIMITIVES]
        if invalid_prims:
            violations.append(f"primitive_stack:unknown:{invalid_prims}")

    # [4] duration 1~30
    duration = scene.get("duration")
    if duration is None:
        violations.append("duration:missing")
    elif not isinstance(duration, (int, float)):
        violations.append("duration:not_numeric")
    elif not (1 <= duration <= 30):
        violations.append(f"duration:out_of_range:{duration} (allowed 1-30)")

    # [5] layout 존재
    layout = scene.get("layout", "")
    if not layout:
        violations.append("layout:empty")
    elif layout not in ALLOWED_LAYOUTS:
        violations.append(f"layout:invalid:{layout}")

    # [6] animation 존재
    animation = scene.get("animation", "")
    if not animation:
        violations.append("animation:empty")
    elif animation not in ALLOWED_ANIMATIONS:
        # [8] 허용 animation만
        violations.append(f"animation:invalid:{animation}")

    return SceneAuditResult(scene_id=scene_id, passed=len(violations) == 0, violations=violations)


# ────────────────────────────────────────────────────────────────
# Public Entry Points
# ────────────────────────────────────────────────────────────────

def audit_specs(specs: list[dict]) -> MotionAuditReport:
    """Motion Spec 배열을 검사하고 MotionAuditReport 반환."""
    global_errors: list[str] = []

    if not isinstance(specs, list):
        report = MotionAuditReport(
            passed=False,
            total_scenes=0,
            passed_scenes=0,
            failed_scenes=0,
            global_errors=["input_not_a_list"],
        )
        report.print_summary()
        return report

    if len(specs) == 0:
        report = MotionAuditReport(
            passed=False,
            total_scenes=0,
            passed_scenes=0,
            failed_scenes=0,
            global_errors=["empty_spec_list"],
        )
        report.print_summary()
        return report

    scene_results = [_audit_scene(scene, i) for i, scene in enumerate(specs)]
    passed_count = sum(1 for r in scene_results if r.passed)
    failed_count = len(scene_results) - passed_count
    overall = failed_count == 0 and len(global_errors) == 0

    report = MotionAuditReport(
        passed=overall,
        total_scenes=len(specs),
        passed_scenes=passed_count,
        failed_scenes=failed_count,
        scene_results=scene_results,
        global_errors=global_errors,
    )
    report.print_summary()
    return report


def audit_file(path: Path) -> MotionAuditReport:
    """JSON 파일을 읽어 audit_specs 실행."""
    if not path.exists():
        report = MotionAuditReport(
            passed=False,
            total_scenes=0,
            passed_scenes=0,
            failed_scenes=0,
            global_errors=[f"file_not_found:{path}"],
        )
        report.print_summary()
        return report

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report = MotionAuditReport(
            passed=False,
            total_scenes=0,
            passed_scenes=0,
            failed_scenes=0,
            global_errors=[f"json_decode_error:{exc}"],
        )
        report.print_summary()
        return report

    return audit_specs(data)


def audit_and_exit(specs: list[dict]) -> None:
    """audit_specs 실행 후 실패 시 sys.exit(1)."""
    import sys
    report = audit_specs(specs)
    if not report.passed:
        log.error("Motion Audit FAILED: %d scenes failed", report.failed_scenes)
        sys.exit(1)
    log.info("Motion Audit PASSED: %d/%d scenes OK", report.passed_scenes, report.total_scenes)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python motion_audit.py <motion_spec.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    report = audit_file(path)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    sys.exit(0 if report.passed else 1)
