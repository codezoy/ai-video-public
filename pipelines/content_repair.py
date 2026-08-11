"""Content Repair Loop — detects repetition, low density, missing concepts, auto-repairs via LLM."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Detection helpers ─────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _algo_repetition_check(scenes: list[dict]) -> list[dict]:
    """Return issues for scenes sharing near-identical titles (Jaccard > 0.75)."""
    issues: list[dict] = []
    titles: list[tuple[int, str]] = []
    for i, scene in enumerate(scenes):
        title = scene.get("title", "").strip()
        if not title:
            titles.append((i + 1, ""))
            continue
        for prev_num, prev_title in titles:
            if not prev_title:
                continue
            sim = _jaccard(title, prev_title)
            if sim > 0.75:
                issues.append({
                    "type": "DUPLICATE_TITLE",
                    "scene_a": prev_num,
                    "scene_b": i + 1,
                    "title_a": prev_title,
                    "title_b": title,
                    "similarity": round(sim, 2),
                })
        titles.append((i + 1, title))
    return issues


def _density_check(scenes: list[dict]) -> list[dict]:
    """Return issues for scenes whose narration_text is under 30 chars."""
    issues: list[dict] = []
    for i, scene in enumerate(scenes):
        narration = (scene.get("narration_text") or scene.get("narration") or "").strip()
        if narration and len(narration) < 30:
            issues.append({
                "type": "LOW_DENSITY",
                "scene_num": i + 1,
                "title": scene.get("title", ""),
                "narration_len": len(narration),
            })
    return issues


def _coverage_check(scenes: list[dict], learning_brief: dict) -> list[dict]:
    """Return issues for key_points/concepts in learning_brief not mentioned in any scene."""
    issues: list[dict] = []
    all_text = " ".join(
        (scene.get("narration_text") or scene.get("narration") or "")
        + " "
        + scene.get("title", "")
        for scene in scenes
    ).lower()

    key_points = learning_brief.get("key_points", [])
    for kp in key_points:
        kp_text = kp if isinstance(kp, str) else kp.get("point", kp.get("text", str(kp)))
        words = [w for w in kp_text.lower().split() if len(w) > 3]
        if words and not any(w in all_text for w in words[:3]):
            issues.append({"type": "MISSING_KEY_POINT", "content": kp_text[:120]})

    concepts = learning_brief.get("concepts", [])
    for concept in concepts:
        c_text = concept if isinstance(concept, str) else concept.get("name", concept.get("term", str(concept)))
        if len(c_text) > 3 and c_text.lower() not in all_text:
            issues.append({"type": "MISSING_CONCEPT", "content": c_text[:80]})

    return issues


# ── LLM repair ────────────────────────────────────────────────────────────────

def _llm_repair(
    scenes: list[dict],
    issues: list[dict],
    topic: str,
    learning_brief: dict,
) -> list[dict]:
    """Ask LLM to patch scenes for the given issues. Returns repaired list or original on failure."""
    try:
        from llm_client import generate as _llm_gen  # noqa: PLC0415

        issues_summary = json.dumps(issues[:20], ensure_ascii=False)

        kp_context = ""
        if learning_brief:
            kp = learning_brief.get("key_points", [])[:5]
            cpts = learning_brief.get("concepts", [])[:5]
            if kp or cpts:
                kp_context = (
                    f"Key Points: {json.dumps(kp, ensure_ascii=False)}\n"
                    f"Concepts: {json.dumps(cpts, ensure_ascii=False)}\n"
                )

        scenes_json_str = json.dumps(scenes, ensure_ascii=False, indent=2)

        prompt = (
            "You are a content repair specialist for educational videos.\n\n"
            f"Topic: {topic}\n"
            f"{kp_context}"
            "\nIssues detected:\n"
            f"{issues_summary}\n\n"
            "Scenes JSON:\n"
            f"{scenes_json_str}\n\n"
            "Instructions:\n"
            "1. DUPLICATE_TITLE: differentiate titles and objectives so each scene is unique\n"
            "2. LOW_DENSITY: expand narration_text to at least 80 chars with meaningful content\n"
            "3. MISSING_KEY_POINT / MISSING_CONCEPT: naturally incorporate into the most relevant scene\n"
            "4. Keep scene count identical; preserve all existing fields\n"
            "5. Return ONLY the repaired scenes array as valid JSON — no markdown, no explanation\n\n"
            "Format: [{\"scene_num\": ..., \"title\": ..., \"narration_text\": ..., ...}, ...]"
        )

        raw = _llm_gen(prompt, role="content_repair")
        raw = raw.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

        repaired = json.loads(raw)
        if isinstance(repaired, list) and len(repaired) == len(scenes):
            return repaired

        logger.warning("[content_repair] LLM returned %d scenes (expected %d) — using original", len(repaired) if isinstance(repaired, list) else -1, len(scenes))
        return scenes

    except Exception as exc:
        logger.warning("[content_repair] LLM repair failed: %s — keeping original scenes", exc)
        return scenes


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    scenes_json: Path,
    run_dir: Path,
    topic: str,
    learning_brief_path: Path | None = None,
    force: bool = False,
) -> dict:
    """
    Detect content issues and optionally repair via LLM.

    Returns:
        {
            "status":  "PASS" | "WARN" | "REPAIR" | "FAIL",
            "issues":  list[dict],
            "repairs": int,
            "elapsed": float,
        }
    """
    t0 = time.monotonic()

    # ── Load scenes ────────────────────────────────────────────────────────────
    if not scenes_json.exists():
        elapsed = time.monotonic() - t0
        return {"status": "FAIL", "issues": [{"type": "SCENES_NOT_FOUND"}], "repairs": 0, "elapsed": elapsed}

    try:
        scenes_data = json.loads(scenes_json.read_text(encoding="utf-8"))
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return {"status": "FAIL", "issues": [{"type": "IO_ERROR", "msg": str(exc)}], "repairs": 0, "elapsed": elapsed}

    scenes = scenes_data.get("scenes", [])
    if not scenes:
        elapsed = time.monotonic() - t0
        return {"status": "FAIL", "issues": [{"type": "EMPTY_SCENES"}], "repairs": 0, "elapsed": elapsed}

    # ── Load learning brief (optional) ────────────────────────────────────────
    learning_brief: dict = {}
    if learning_brief_path is None:
        learning_brief_path = run_dir / "content_adapter" / "learning_brief.json"
    if learning_brief_path.exists():
        try:
            learning_brief = json.loads(learning_brief_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[content_repair] learning_brief.json load failed: %s", exc)

    # ── Detection phase ────────────────────────────────────────────────────────
    issues: list[dict] = []
    issues.extend(_algo_repetition_check(scenes))
    issues.extend(_density_check(scenes))
    if learning_brief:
        issues.extend(_coverage_check(scenes, learning_brief))

    # ── Determine status and repair ────────────────────────────────────────────
    has_duplicate = any(i["type"] == "DUPLICATE_TITLE" for i in issues)
    repairs = 0

    if not issues:
        status = "PASS"
        repaired_scenes = scenes
    elif len(issues) <= 2 and not has_duplicate:
        status = "WARN"
        repaired_scenes = scenes
    else:
        status = "REPAIR"
        repaired_scenes = _llm_repair(scenes, issues, topic, learning_brief)
        if repaired_scenes is not scenes:
            scenes_data["scenes"] = repaired_scenes
            scenes_json.write_text(json.dumps(scenes_data, ensure_ascii=False, indent=2), encoding="utf-8")
            repairs = sum(1 for i in issues if i["type"] in ("DUPLICATE_TITLE", "LOW_DENSITY"))

    elapsed = time.monotonic() - t0

    # ── Save artifacts ─────────────────────────────────────────────────────────
    guard_dir = run_dir / "guard"
    guard_dir.mkdir(parents=True, exist_ok=True)

    (guard_dir / "content_repair_raw.json").write_text(
        json.dumps(
            {
                "topic": topic,
                "scene_count": len(scenes),
                "learning_brief_available": bool(learning_brief),
                "issues": issues,
                "elapsed_sec": round(elapsed, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (guard_dir / "content_repair_report.json").write_text(
        json.dumps(
            {
                "status": status,
                "issue_count": len(issues),
                "issue_types": list({i["type"] for i in issues}),
                "repairs": repairs,
                "learning_brief_available": bool(learning_brief),
                "elapsed_sec": round(elapsed, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {"status": status, "issues": issues, "repairs": repairs, "elapsed": elapsed}
