"""Primitive Renderer — Motion Spec JSON → Hyperframe PrimitiveTree JSON.

MVP Scope
  Primitives : Hero, Compare, Highlight, Summary
  Scene Types: compare, summary
  Animations : fade_in, slide_in, none
  Providers  : codex_cli, gemini_cli (upstream; renderer is provider-agnostic)

Pipeline
  motion_spec.json
  └─ MotionAudit       (validate)
  └─ PrimitiveResolver (scene_type → primitive_stack)
  └─ PropsInjector     (scene fields → primitive props)
  └─ AnimationBinder   (animation name → AnimationConfig + stagger)
  └─ PrimitiveTreeBuilder
  └─ PrimitiveRenderer (save to work/motion/primitive_tree.json)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow direct execution from any working directory
sys.path.insert(0, str(Path(__file__).parent))
from motion_audit import ALLOWED_PRIMITIVES, MotionAuditReport, audit_specs  # noqa: E402

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_WORK_MOTION_DIR = _PROJECT_ROOT / "work" / "motion"

FPS: int = 24

# ────────────────────────────────────────────────────────────────
# Catalog Mapping — scene_type → default primitive_stack
# ────────────────────────────────────────────────────────────────

CATALOG_MAPPING: dict[str, list[str]] = {
    "compare": ["Hero", "Compare", "Highlight"],
    "summary": ["Summary"],
    "intro": ["Hero"],
    "concept": ["Hero", "Highlight"],
    "timeline": ["Hero", "Timeline"],
    "code": ["Hero", "CodeBlock"],
    "list": ["Hero", "List"],
    "quote": ["Quote"],
    "stats": ["Hero", "Stats"],
    "outro": ["Hero"],
}

# MVP-supported primitives (subset of full catalog)
MVP_PRIMITIVES: frozenset[str] = frozenset({"Hero", "Compare", "Highlight", "Summary"})

# Animation base configs
_ANIMATION_BASE: dict[str, dict[str, Any]] = {
    "fade_in":  {"name": "fade_in",  "duration_ms": 600, "easing": "ease_out"},
    "slide_in": {"name": "slide_in", "duration_ms": 800, "easing": "ease_out"},
    "none":     {"name": "none",     "duration_ms": 0,   "easing": "linear"},
}
_ANIMATION_FALLBACK: dict[str, Any] = {"name": "fade_in", "duration_ms": 600, "easing": "ease_out"}


# ────────────────────────────────────────────────────────────────
# Sprint 2 — PrimitiveResolver
# ────────────────────────────────────────────────────────────────

class PrimitiveResolver:
    """Determines the final primitive_stack for a scene.

    Priority:
      1. primitive_stack from Motion Spec (if present and all entries are allowed)
      2. CATALOG_MAPPING[scene_type] fallback
      3. ["Hero"] minimum default
    """

    def resolve(self, motion_spec: dict) -> list[str]:
        pstack = motion_spec.get("primitive_stack")
        if (
            pstack
            and isinstance(pstack, list)
            and len(pstack) >= 1
            and all(isinstance(p, str) and p in ALLOWED_PRIMITIVES for p in pstack)
        ):
            log.debug("[RESOLVER] using spec primitive_stack=%s", pstack)
            return list(pstack)

        scene_type = motion_spec.get("scene_type", "")
        if scene_type in CATALOG_MAPPING:
            fallback = CATALOG_MAPPING[scene_type]
            log.debug("[RESOLVER] catalog fallback scene_type=%s → %s", scene_type, fallback)
            return list(fallback)

        log.debug("[RESOLVER] default → [Hero]")
        return ["Hero"]


# ────────────────────────────────────────────────────────────────
# Sprint 3 — PropsInjector
# ────────────────────────────────────────────────────────────────

class PropsInjector:
    """Maps scene spec fields to Primitive-specific Props dictionaries."""

    def inject(self, primitive_type: str, scene_spec: dict) -> dict:
        method_name = f"_inject_{primitive_type.lower()}"
        handler = getattr(self, method_name, self._inject_default)
        return handler(scene_spec)

    def _inject_hero(self, s: dict) -> dict:
        title = s.get("heading") or s.get("title") or None
        if not title:
            title = s.get("scene_id", "")
            log.warning(
                "[TitleFallback] scene=%s reason=missing_title source=scene_id",
                s.get("scene_id", "unknown"),
            )
        return {
            "title": title,
            "subtitle": s.get("subheading") or s.get("subtitle"),
            "emphasis": list(s.get("emphasis") or []),
            "eyebrow": s.get("eyebrow"),
            "layout": "centered",
        }

    def _inject_compare(self, s: dict) -> dict:
        left = s.get("left_content") or s.get("left_items") or []
        right = s.get("right_content") or s.get("right_items") or []
        if isinstance(left, str):
            left = [left]
        if isinstance(right, str):
            right = [right]
        return {
            "leftTitle": s.get("left_title", "Before"),
            "rightTitle": s.get("right_title", "After"),
            "leftItems": list(left),
            "rightItems": list(right),
            "highlightSide": s.get("highlight_side", "right"),
        }

    def _inject_highlight(self, s: dict) -> dict:
        return {
            "content": s.get("narration") or s.get("content") or "",
            "highlights": list(s.get("emphasis") or []),
        }

    def _inject_summary(self, s: dict) -> dict:
        points = s.get("key_points") or s.get("points") or []
        if isinstance(points, str):
            points = [points]
        return {
            "title": s.get("heading") or s.get("title") or "Summary",
            "points": list(points),
        }

    def _inject_default(self, s: dict) -> dict:
        return {
            "content": s.get("narration") or s.get("content") or "",
            "emphasis": list(s.get("emphasis") or []),
        }


# ────────────────────────────────────────────────────────────────
# Sprint 4 — AnimationBinder
# ────────────────────────────────────────────────────────────────

class AnimationBinder:
    """Produces an AnimationConfig dict with stagger delay for a primitive."""

    def bind(
        self,
        animation_name: str,
        index: int,
        total: int,
        scene_duration_frames: int,
    ) -> dict:
        """Return AnimationConfig with computed stagger delay_ms."""
        base = dict(_ANIMATION_BASE.get(animation_name, _ANIMATION_FALLBACK))

        scene_duration_ms = (scene_duration_frames / FPS) * 1000
        delay_ms = int(index * (scene_duration_ms / max(total, 1) / 2)) if total > 1 else 0
        base["delay_ms"] = delay_ms
        return base


# ────────────────────────────────────────────────────────────────
# Sprint 5 — PrimitiveTreeBuilder
# ────────────────────────────────────────────────────────────────

class PrimitiveTreeBuilder:
    """Assembles a serializable PrimitiveTree for a single scene."""

    def __init__(self) -> None:
        self._resolver = PrimitiveResolver()
        self._injector = PropsInjector()
        self._binder = AnimationBinder()

    def build(self, scene_spec: dict) -> dict:
        """Build one PrimitiveTree dict from a Motion Spec scene entry."""
        duration_sec: float = float(scene_spec.get("duration", 5))
        duration_frames: int = int(duration_sec * FPS)
        animation_name: str = scene_spec.get("animation", "fade_in")
        layout: str = scene_spec.get("layout", "full")

        primitives_list = self._resolver.resolve(scene_spec)
        total = len(primitives_list)

        primitives: list[dict] = []
        for idx, prim_type in enumerate(primitives_list):
            props = self._injector.inject(prim_type, scene_spec)
            anim = self._binder.bind(animation_name, idx, total, duration_frames)
            primitives.append({
                "type": prim_type,
                "props": props,
                "animation": anim,
                "z_index": idx,
            })

        tree: dict = {
            "scene_id": scene_spec.get("scene_id", "scene_unknown"),
            "duration_frames": duration_frames,
            "fps": FPS,
            "layout": layout,
            "background": "#000000",
            "primitives": primitives,
        }
        # motion_spec의 title/heading을 primitive_tree root에 전달 (HyperframePropsBuilder 참조용)
        title = scene_spec.get("title") or scene_spec.get("heading")
        if title:
            tree["title"] = title
        return tree


# ────────────────────────────────────────────────────────────────
# Sprint 6 — PrimitiveRenderer (Hyperframe Adapter)
# ────────────────────────────────────────────────────────────────

class PrimitiveRenderer:
    """Main entry: Motion Spec list → PrimitiveTree JSON.

    Saves output to work/motion/primitive_tree.json (Hyperframe-consumable).
    TSX generation is out of scope for MVP.
    """

    def __init__(self, out_dir: Path | None = None) -> None:
        self._out_dir = out_dir or _WORK_MOTION_DIR
        self._builder = PrimitiveTreeBuilder()

    def render(self, specs: list[dict], skip_audit: bool = False) -> list[dict]:
        """Audit → build PrimitiveTrees. Returns list of tree dicts."""
        if not skip_audit:
            report: MotionAuditReport = audit_specs(specs)
            if not report.passed:
                log.error("[PRIMITIVE_RENDERER] Audit FAILED — aborting render")
                sys.exit(1)

        trees = [self._builder.build(spec) for spec in specs]
        log.info("[PRIMITIVE_RENDERER] built %d primitive tree(s)", len(trees))
        return trees

    def render_and_save(
        self,
        specs: list[dict],
        filename: str = "primitive_tree.json",
        skip_audit: bool = False,
    ) -> Path:
        """Render specs and persist as JSON. Returns output path."""
        trees = self.render(specs, skip_audit=skip_audit)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._out_dir / filename
        out_path.write_text(
            json.dumps(trees, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("[PRIMITIVE_RENDERER] saved → %s", out_path)
        return out_path


def render_motion_spec(
    specs: list[dict],
    out_dir: Path | None = None,
    filename: str = "primitive_tree.json",
) -> Path:
    """Convenience function: audit → render → save → return path."""
    return PrimitiveRenderer(out_dir=out_dir).render_and_save(specs, filename=filename)


# ────────────────────────────────────────────────────────────────
# Sprint 7 — Validation (CLI entry)
# ────────────────────────────────────────────────────────────────

_COMPARE_SPEC: list[dict] = [
    {
        "scene_id": "scene01",
        "scene_type": "compare",
        "layout": "left_right",
        "animation": "fade_in",
        "duration": 8,
        "heading": "기존 LLM vs RAG",
        "left_title": "기존 LLM",
        "right_title": "RAG",
        "left_content": ["학습 데이터만 사용", "최신 정보 없음", "환각 발생"],
        "right_content": ["외부 검색 활용", "실시간 정보 주입", "정확도 향상"],
        "emphasis": ["RAG", "검색"],
        "primitive_stack": ["Hero", "Compare", "Highlight"],
    }
]

_SUMMARY_SPEC: list[dict] = [
    {
        "scene_id": "scene02",
        "scene_type": "summary",
        "layout": "full",
        "animation": "slide_in",
        "duration": 6,
        "heading": "핵심 정리",
        "key_points": [
            "RAG는 검색과 생성을 결합한다",
            "외부 문서로 LLM 지식을 보강한다",
            "환각을 줄이고 정확도를 높인다",
        ],
        "primitive_stack": ["Summary"],
    }
]

_BAD_PRIMITIVE_SPEC: list[dict] = [
    {
        "scene_id": "scene_bad",
        "scene_type": "compare",
        "layout": "full",
        "animation": "fade_in",
        "duration": 5,
        "primitive_stack": ["InvalidPrimitive"],
    }
]

_BAD_ANIMATION_SPEC: list[dict] = [
    {
        "scene_id": "scene_bad_anim",
        "scene_type": "compare",
        "layout": "full",
        "animation": "invalid_animation",
        "duration": 5,
        "primitive_stack": ["Hero"],
    }
]


def _run_validation() -> None:
    """Sprint 7: Run all 5 validation cases and report results."""
    from motion_audit import audit_specs

    results: list[tuple[str, bool]] = []
    builder = PrimitiveTreeBuilder()

    # Case 1: compare → PrimitiveTree 생성
    audit1 = audit_specs(_COMPARE_SPEC)
    if audit1.passed:
        tree1 = builder.build(_COMPARE_SPEC[0])
        case1_ok = tree1["scene_id"] == "scene01" and len(tree1["primitives"]) == 3
    else:
        case1_ok = False
    results.append(("Case 1: compare → PrimitiveTree", case1_ok))

    # Case 2: summary → PrimitiveTree 생성
    audit2 = audit_specs(_SUMMARY_SPEC)
    if audit2.passed:
        tree2 = builder.build(_SUMMARY_SPEC[0])
        case2_ok = tree2["scene_id"] == "scene02" and len(tree2["primitives"]) == 1
    else:
        case2_ok = False
    results.append(("Case 2: summary → PrimitiveTree", case2_ok))

    # Case 3: 잘못된 Primitive → Audit FAIL
    audit3 = audit_specs(_BAD_PRIMITIVE_SPEC)
    results.append(("Case 3: bad primitive → Audit FAIL", not audit3.passed))

    # Case 4: 잘못된 Animation → Audit FAIL
    audit4 = audit_specs(_BAD_ANIMATION_SPEC)
    results.append(("Case 4: bad animation → Audit FAIL", not audit4.passed))

    # Case 5: Motion Mode → Renderer → primitive_tree.json
    try:
        renderer = PrimitiveRenderer()
        out_path = renderer.render_and_save(_COMPARE_SPEC + _SUMMARY_SPEC)
        case5_ok = out_path.exists()
    except SystemExit:
        case5_ok = False
    results.append(("Case 5: render_and_save → primitive_tree.json", case5_ok))

    # Print results
    print("\n[PRIMITIVE_RENDERER] Validation Results:")
    all_pass = True
    for label, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {label}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("[PRIMITIVE_RENDERER] ALL CASES PASS")
    else:
        print("[PRIMITIVE_RENDERER] SOME CASES FAILED")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Primitive Renderer")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="render a motion_spec.json")
    run_p.add_argument("spec_file", help="path to motion_spec.json")
    run_p.add_argument("--out-dir", help="output directory (default: work/motion)")

    sub.add_parser("validate", help="run Sprint 7 validation cases")

    args = parser.parse_args()

    if args.cmd == "run":
        spec_path = Path(args.spec_file)
        if not spec_path.exists():
            log.error("File not found: %s", spec_path)
            sys.exit(1)
        specs = json.loads(spec_path.read_text(encoding="utf-8"))
        out = render_motion_spec(specs, out_dir=Path(args.out_dir) if args.out_dir else None)
        print(f"[PRIMITIVE_RENDERER] → {out}")

    elif args.cmd == "validate":
        _run_validation()

    else:
        # Default: run validation
        _run_validation()
