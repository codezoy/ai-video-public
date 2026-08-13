"""Visual Audit Pipeline — hyperframe_scenes.json → visual_audit.json.

Tasks covered:
  TASK-002: Title Placeholder Detection
  TASK-003: Composition Diversity Audit
  TASK-004: Primitive Diversity Audit
  TASK-005: Visual Score Engine (100-point scoring)

Usage:
  python pipelines/visual_audit.py
  python pipelines/visual_audit.py --source work/motion/hyperframe_scenes.json
  python pipelines/visual_audit.py --out work/visual_audit.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_SOURCE = _PROJECT_ROOT / "work" / "motion" / "hyperframe_scenes.json"
_DEFAULT_OUT    = _PROJECT_ROOT / "work" / "visual_audit.json"

# ────────────────────────────────────────────────────────────────
# Schema Normalization — pipeline scenes.json → hyperframe schema
# ────────────────────────────────────────────────────────────────

_TEMPLATE_TO_COMPOSITION: dict[str, str] = {
    "hero_title":       "TitleOpen",
    "bullet_list":      "Explain",
    "flow_steps":       "Explain",
    "compare":          "CompareTwo",
    "compare_two":      "CompareTwo",
    "quote_highlight":  "Quote",
    "before_after":     "CompareTwo",
    "timeline":         "Timeline",
    "explain":          "Explain",
    "summary":          "SummaryCard",
    "summary_card":     "SummaryCard",
    "code":             "Explain",
    "card":             "SummaryCard",
    "architecture_tree": "Diagram",
    "table_compare":    "TableCompare",
}

_VISUAL_TYPE_TO_PRIMITIVES: dict[str, list[str]] = {
    "text":     ["List"],
    "diagram":  ["Diagram"],
    "code":     ["CodeBlock"],
    "compare":  ["Compare"],
    "timeline": ["Timeline"],
    "hero":     ["Hero"],
    "stats":    ["Stats"],
    "quote":    ["Quote"],
}

_TEMPLATE_EXTRA_PRIMITIVES: dict[str, list[str]] = {
    "hero_title":    ["Hero"],
    "flow_steps":    ["List", "Highlight"],
    "bullet_list":   ["Highlight"],
    "summary":       ["CTA"],
    "summary_card":  ["Summary", "CTA"],
    "compare":          ["Compare"],
    "compare_two":      ["Compare"],
    "quote_highlight":  ["Quote"],
    "before_after":     ["Compare"],
    "timeline":         ["Timeline"],
    "architecture_tree": ["Diagram"],
    "table_compare":    ["Compare"],
}


def _infer_primitives(scene: dict[str, Any]) -> list[str]:
    prims: list[str] = []
    vtype = str(scene.get("visual_type", "text"))
    ttype = str(scene.get("template_type", ""))
    prims.extend(_VISUAL_TYPE_TO_PRIMITIVES.get(vtype, ["List"]))
    prims.extend(_TEMPLATE_EXTRA_PRIMITIVES.get(ttype, []))
    if scene.get("mermaid"):
        prims.append("Diagram")
    if scene.get("code_block"):
        prims.append("CodeBlock")
    if scene.get("card"):
        prims.append("Stats")
    return list(dict.fromkeys(prims))  # deduplicate, preserve order


def _normalize_scene(scene: dict[str, Any]) -> dict[str, Any]:
    """Map pipeline scenes.json fields to hyperframe audit schema."""
    if "scene_id" in scene:
        return scene  # already hyperframe schema

    bullets_raw = scene.get("bullets", [])
    bullet_texts = [b["text"] if isinstance(b, dict) else str(b) for b in bullets_raw]

    vd: dict[str, Any] = scene.get("visual_data") or {}
    # Templates with keyword-style visual_data store extra content as keywords.
    kw = vd.get("keywords", [])
    if kw:
        bullet_texts = bullet_texts + [str(k) for k in kw]

    steps = vd.get("steps", [])
    nodes = vd.get("nodes", [])  # architecture_tree uses 'nodes'
    events = vd.get("events", steps or nodes)  # timeline→events, flow_steps→steps, arch_tree→nodes
    left_items  = vd.get("left_items", [])
    right_items = vd.get("right_items", [])
    takeaways   = vd.get("takeaways", [])

    return {
        "scene_id":         str(scene.get("id", "?")),
        "composition":      _TEMPLATE_TO_COMPOSITION.get(
                                str(scene.get("template_type", "")), "Explain"),
        "fps":              scene.get("fps", 30),
        "duration_frames":  scene.get("render_duration_frames", 0),
        "source_primitives": _infer_primitives(scene),
        "props": {
            "title":      scene.get("title", ""),
            "bullets":    bullet_texts,
            "events":     [str(e) for e in events],
            "left_items": [str(i) for i in left_items],
            "right_items":[str(i) for i in right_items],
            "takeaways":  [str(t) for t in takeaways],
        },
        "_original": scene,
    }


def _normalize_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_scene(s) for s in scenes]

# ────────────────────────────────────────────────────────────────
# TASK-002 — Title Placeholder Detection
# ────────────────────────────────────────────────────────────────

TITLE_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^scene\d+$",       re.IGNORECASE),
    re.compile(r"^untitled\d*$",    re.IGNORECASE),
    re.compile(r"^씬\s*\d+$"),
    re.compile(r"^제목\s*\d*$"),
    re.compile(r"^title\s*\d*$",    re.IGNORECASE),
    re.compile(r"^\s*$"),
]

KNOWN_COMPOSITIONS: frozenset[str] = frozenset({
    "TitleOpen", "CompareTwo", "SummaryCard", "Timeline", "Explain",
    "Diagram", "TableCompare",
})

KNOWN_PRIMITIVES: frozenset[str] = frozenset({
    "Hero", "Compare", "Diagram", "Timeline", "Highlight",
    "Summary", "CTA", "Stats", "List", "CodeBlock", "Quote",
})


def _is_placeholder_title(title: str) -> bool:
    return any(p.match(title.strip()) for p in TITLE_PLACEHOLDER_PATTERNS)


@dataclass
class TitleAuditResult:
    placeholder_detected: bool
    placeholder_scenes: list[str]
    empty_title_scenes: list[str]
    total_scenes: int

    @property
    def quality_score(self) -> float:
        bad = len(self.placeholder_scenes) + len(self.empty_title_scenes)
        if self.total_scenes == 0:
            return 0.0
        ratio = bad / self.total_scenes
        return round(max(0.0, 20.0 * (1.0 - ratio)), 2)


def audit_titles(scenes: list[dict[str, Any]]) -> TitleAuditResult:
    placeholder: list[str] = []
    empty: list[str] = []

    for scene in scenes:
        sid = scene.get("scene_id", "?")
        title = str(scene.get("props", {}).get("title", "")).strip()
        if not title:
            empty.append(sid)
        elif _is_placeholder_title(title):
            placeholder.append(sid)

    return TitleAuditResult(
        placeholder_detected=bool(placeholder),
        placeholder_scenes=placeholder,
        empty_title_scenes=empty,
        total_scenes=len(scenes),
    )


# ────────────────────────────────────────────────────────────────
# TASK-003 — Composition Diversity Audit
# ────────────────────────────────────────────────────────────────

@dataclass
class CompositionAuditResult:
    composition_count: int
    unique_compositions: list[str]
    distribution: dict[str, int]
    unknown_compositions: list[str]
    composition_diversity_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_compositions(scenes: list[dict[str, Any]]) -> CompositionAuditResult:
    compositions = [str(s.get("composition", "")).strip() for s in scenes]
    counter = Counter(compositions)
    unique = sorted(counter.keys())
    unknown = [c for c in unique if c not in KNOWN_COMPOSITIONS]

    n = len(scenes)
    unique_count = len(unique)
    raw_score = (unique_count / max(n, 1)) * 20.0
    score = round(min(20.0, raw_score), 2)

    return CompositionAuditResult(
        composition_count=unique_count,
        unique_compositions=unique,
        distribution=dict(counter),
        unknown_compositions=unknown,
        composition_diversity_score=score,
    )


# ────────────────────────────────────────────────────────────────
# TASK-004 — Primitive Diversity Audit
# ────────────────────────────────────────────────────────────────

@dataclass
class PrimitiveAuditResult:
    primitive_count: int
    unique_primitives: list[str]
    distribution: dict[str, int]
    unknown_primitives: list[str]
    primitive_diversity_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_primitives(scenes: list[dict[str, Any]]) -> PrimitiveAuditResult:
    all_prims: list[str] = []
    for scene in scenes:
        prims = scene.get("source_primitives", [])
        if isinstance(prims, list):
            all_prims.extend(str(p) for p in prims)

    counter = Counter(all_prims)
    unique = sorted(counter.keys())
    unknown = [p for p in unique if p not in KNOWN_PRIMITIVES]

    max_prims = len(KNOWN_PRIMITIVES)
    score = round(min(20.0, (len(unique) / max_prims) * 20.0), 2)

    return PrimitiveAuditResult(
        primitive_count=len(unique),
        unique_primitives=unique,
        distribution=dict(counter),
        unknown_primitives=unknown,
        primitive_diversity_score=score,
    )


# ────────────────────────────────────────────────────────────────
# Information Density Auditor (supporting metric)
# ────────────────────────────────────────────────────────────────

def _count_items(scene: dict[str, Any]) -> int:
    props = scene.get("props", {})
    counts = [
        len(props.get("bullets", [])),
        len(props.get("events", [])),
        len(props.get("left_items", [])),
        len(props.get("right_items", [])),
        len(props.get("takeaways", [])),
    ]
    return sum(counts)


def audit_information_density(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    if not scenes:
        return {"avg_items_per_scene": 0, "density_score": 0.0}
    totals = [_count_items(s) for s in scenes]
    avg = sum(totals) / len(totals)
    score = round(min(20.0, avg / 4.0 * 20.0), 2)
    return {
        "avg_items_per_scene": round(avg, 2),
        "per_scene": {s.get("scene_id", f"scene{i}"): totals[i]
                      for i, s in enumerate(scenes)},
        "density_score": score,
    }


# ────────────────────────────────────────────────────────────────
# Visual Consistency Auditor (supporting metric)
# ────────────────────────────────────────────────────────────────

def audit_visual_consistency(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    if not scenes:
        return {"missing_fields": [], "consistency_score": 0.0}

    required = ["scene_id", "composition", "fps", "duration_frames"]
    issues: list[str] = []

    fps_values: set[int] = set()
    for scene in scenes:
        sid = scene.get("scene_id", "?")
        for fld in required:
            if fld not in scene or scene[fld] is None:
                issues.append(f"{sid}.{fld}")
        if "fps" in scene:
            fps_values.add(scene["fps"])

    fps_consistent = len(fps_values) <= 1
    ratio_ok = 1.0 - (len(issues) / max(1, len(scenes) * len(required)))
    score = round(max(0.0, min(20.0, ratio_ok * 20.0 * (1.0 if fps_consistent else 0.9))), 2)

    return {
        "missing_fields": issues,
        "fps_values": sorted(fps_values),
        "fps_consistent": fps_consistent,
        "consistency_score": score,
    }


# ────────────────────────────────────────────────────────────────
# TASK-005 — Visual Score Engine
# ────────────────────────────────────────────────────────────────

PASS_THRESHOLD = 70
WARN_THRESHOLD = 50


@dataclass
class VisualScore:
    title_quality: float
    composition_diversity: float
    primitive_diversity: float
    information_density: float
    visual_consistency: float
    total: float
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title_quality":         {"score": self.title_quality,         "max": 20},
            "composition_diversity": {"score": self.composition_diversity,  "max": 20},
            "primitive_diversity":   {"score": self.primitive_diversity,    "max": 20},
            "information_density":   {"score": self.information_density,    "max": 20},
            "visual_consistency":    {"score": self.visual_consistency,     "max": 20},
            "total":   self.total,
            "verdict": self.verdict,
        }


def compute_visual_score(
    title: TitleAuditResult,
    comp: CompositionAuditResult,
    prim: PrimitiveAuditResult,
    density: dict[str, Any],
    consistency: dict[str, Any],
) -> VisualScore:
    tq  = title.quality_score
    cd  = comp.composition_diversity_score
    pd  = prim.primitive_diversity_score
    idd = density["density_score"]
    vc  = consistency["consistency_score"]

    total = round(tq + cd + pd + idd + vc, 2)
    verdict = "PASS" if total >= PASS_THRESHOLD else ("WARN" if total >= WARN_THRESHOLD else "FAIL")

    return VisualScore(
        title_quality=tq,
        composition_diversity=cd,
        primitive_diversity=pd,
        information_density=idd,
        visual_consistency=vc,
        total=total,
        verdict=verdict,
    )


# ────────────────────────────────────────────────────────────────
# Issue & Recommendation Builder
# ────────────────────────────────────────────────────────────────

def _build_issues(
    title: TitleAuditResult,
    comp: CompositionAuditResult,
    prim: PrimitiveAuditResult,
    score: VisualScore,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    if title.placeholder_scenes:
        issues.append({
            "type": "TITLE_PLACEHOLDER",
            "severity": "HIGH",
            "scenes": ", ".join(title.placeholder_scenes),
            "message": f"Placeholder titles detected in scenes: {title.placeholder_scenes}",
        })

    if title.empty_title_scenes:
        issues.append({
            "type": "EMPTY_TITLE",
            "severity": "HIGH",
            "scenes": ", ".join(title.empty_title_scenes),
            "message": f"Empty titles in scenes: {title.empty_title_scenes}",
        })

    if comp.composition_diversity_score < 12:
        issues.append({
            "type": "LOW_COMPOSITION_DIVERSITY",
            "severity": "MEDIUM",
            "message": f"Only {comp.composition_count} unique composition(s). Add variety.",
        })

    if prim.primitive_diversity_score < 12:
        issues.append({
            "type": "LOW_PRIMITIVE_DIVERSITY",
            "severity": "MEDIUM",
            "message": f"Only {prim.primitive_count} unique primitive(s). Consider Hero/CTA/Diagram.",
        })

    if comp.unknown_compositions:
        issues.append({
            "type": "UNKNOWN_COMPOSITION",
            "severity": "LOW",
            "message": f"Unregistered compositions: {comp.unknown_compositions}",
        })

    if prim.unknown_primitives:
        issues.append({
            "type": "UNKNOWN_PRIMITIVE",
            "severity": "LOW",
            "message": f"Unregistered primitives: {prim.unknown_primitives}",
        })

    return issues


def _build_recommendations(
    issues: list[dict[str, str]],
    score: VisualScore,
) -> list[str]:
    recs: list[str] = []
    issue_types = {i["type"] for i in issues}

    if "TITLE_PLACEHOLDER" in issue_types or "EMPTY_TITLE" in issue_types:
        recs.append("TASK: Replace placeholder/empty titles with meaningful Korean titles")

    if "LOW_COMPOSITION_DIVERSITY" in issue_types:
        recs.append("TASK: Add TitleOpen (intro) and SummaryCard (outro) compositions")

    if "LOW_PRIMITIVE_DIVERSITY" in issue_types:
        recs.append("TASK: Incorporate CTA, Diagram primitives in appropriate scenes")

    if score.information_density < 10:
        recs.append("TASK: Increase bullet/item count per scene (target: 3~5 items/scene)")

    if score.total < PASS_THRESHOLD:
        recs.append("TASK: Run /hchain visual-quality-fix to systematically address FAIL items")

    return recs


# ────────────────────────────────────────────────────────────────
# Main Orchestrator
# ────────────────────────────────────────────────────────────────

def run_audit(source: Path, out: Path) -> dict[str, Any]:
    if not source.exists():
        log.error("[AUDIT] Source not found: %s", source)
        sys.exit(1)

    raw = json.loads(source.read_text(encoding="utf-8"))
    # Support both bare JSON arrays and pipeline scenes.json {"scenes": [...]}
    if isinstance(raw, dict):
        scenes = raw.get("scenes", [])
        log.info("[AUDIT] Detected pipeline dict schema — extracting 'scenes' array")
    elif isinstance(raw, list):
        scenes = raw
    else:
        log.error("[AUDIT] Expected JSON array or dict, got %s", type(raw).__name__)
        sys.exit(1)

    if not scenes:
        log.error("[AUDIT] No scenes found in %s", source)
        sys.exit(1)

    scenes = _normalize_scenes(scenes)
    log.info("[AUDIT] Loaded %d scenes from %s", len(scenes), source)

    title_result   = audit_titles(scenes)
    comp_result    = audit_compositions(scenes)
    prim_result    = audit_primitives(scenes)
    density_result = audit_information_density(scenes)
    consist_result = audit_visual_consistency(scenes)
    score          = compute_visual_score(
        title_result, comp_result, prim_result, density_result, consist_result
    )
    issues         = _build_issues(title_result, comp_result, prim_result, score)
    recommendations = _build_recommendations(issues, score)

    report: dict[str, Any] = {
        "audit_version": "1.0.0",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source),
        "scene_count": len(scenes),
        "title_audit": {
            "placeholder_detected": title_result.placeholder_detected,
            "placeholder_scenes": title_result.placeholder_scenes,
            "empty_title_scenes": title_result.empty_title_scenes,
        },
        "composition_audit": {
            "composition_count": comp_result.composition_count,
            "unique_compositions": comp_result.unique_compositions,
            "distribution": comp_result.distribution,
            "unknown_compositions": comp_result.unknown_compositions,
            "composition_diversity_score": comp_result.composition_diversity_score,
        },
        "primitive_audit": {
            "primitive_count": prim_result.primitive_count,
            "unique_primitives": prim_result.unique_primitives,
            "distribution": prim_result.distribution,
            "unknown_primitives": prim_result.unknown_primitives,
            "primitive_diversity_score": prim_result.primitive_diversity_score,
        },
        "information_density": density_result,
        "visual_consistency": consist_result,
        "visual_score": score.to_dict(),
        "issues": issues,
        "recommendations": recommendations,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[AUDIT] Report written to %s", out)
    log.info("[AUDIT] Visual Score: %s / 100  (%s)", score.total, score.verdict)

    return report


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Visual Audit Pipeline")
    p.add_argument("--source", type=Path, default=_DEFAULT_SOURCE,
                   help="Input hyperframe_scenes.json (default: work/motion/hyperframe_scenes.json)")
    p.add_argument("--out",    type=Path, default=_DEFAULT_OUT,
                   help="Output visual_audit.json (default: work/visual_audit.json)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    report = run_audit(args.source, args.out)
    score = report["visual_score"]
    print(f"\n{'='*50}")
    print(f"  Visual Score : {score['total']} / 100")
    print(f"  Verdict      : {score['verdict']}")
    print(f"  Issues       : {len(report['issues'])}")
    print(f"  Output       : {args.out}")
    print(f"{'='*50}\n")

    if score["verdict"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
