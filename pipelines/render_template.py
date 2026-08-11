"""Python → Node CLI bridge for Remotion template rendering."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_HYPERFRAME_DIR = _PROJECT_ROOT / "hyperframe"
_FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

# Maps template_type → Remotion composition ID (PascalCase)
# Includes both new lowercase types and legacy UPPER_SNAKE_CASE for backward compat
_COMPOSITION_ID: dict[str, str] = {
    # dedicated compositions — all template types
    "hero_title":        "TitleOpen",
    "flow_steps":        "FlowSteps",
    "architecture_tree": "ArchTree",
    "timeline":          "Timeline",
    "compare_two":       "CompareTwo",
    "table_compare":     "TableCompare",
    "keyword_cards":     "KeywordCards",
    "summary_card":      "SummaryCard",
    "quote_highlight":   "Quote",
    "before_after":      "CompareTwo",
    # LOW-difficulty templates (Phase 1 expansion)
    "split_title":        "SplitTitle",
    "underline_title":    "UnderlineTitle",
    "side_accent_title":  "SideAccentTitle",
    "glass_cards":        "GlassCards",
    "border_cards":       "BorderCards",
    "number_badge_list":  "NumberBadgeList",
    "pill_tags":          "PillTags",
    "fullscreen_text":    "FullscreenText",
    "two_column_text":    "TwoColumnText",
    "callout_box":        "CalloutBox",
    "bracket_emphasis":   "BracketEmphasis",
    "slide_in_list":      "SlideInList",
    "scale_pop_cards":    "ScalePopCards",
    # Developer / AI Engineer compositions (Phase 2)
    "code_editor":           "CodeEditorComposition",
    "terminal":              "TerminalComposition",
    "chat_conversation":     "ChatConversationComposition",
    "architecture_diagram":  "ArchitectureDiagramComposition",
    "agent_workflow":        "AgentWorkflowComposition",
    # Variant templates (Phase 3 — visual diversity)
    "keyword_cards_grid":  "KeywordCards",
    "keyword_cards_stack": "KeywordCards",
    "timeline_zigzag":     "Timeline",
    "timeline_cards":      "Timeline",
    "flow_steps_circle":   "FlowSteps",
    "flow_steps_stair":    "FlowSteps",
    "summary_card_split":  "CompareTwo",
    "compare_three":       "TableCompare",
    # legacy UPPER_SNAKE_CASE types (backward compat)
    "TITLE_OPEN":  "TitleOpen",
    "EXPLAIN":     "Explain",
    "LIST_REVEAL": "ListReveal",
    "QUOTE":       "Quote",
    "OUTRO_CTA":   "OutroCta",
}


def _check_node_env() -> None:
    if not (_HYPERFRAME_DIR / "node_modules").exists():
        log.info("node_modules not found — running npm install in %s", _HYPERFRAME_DIR)
        result = subprocess.run(
            ["npm", "install"],
            cwd=_HYPERFRAME_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"npm install failed:\n{result.stderr}")


def render_scene(
    scene: dict[str, Any],
    output_path: Path,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    force: bool = False,
) -> Path:
    """Render a single scene using Remotion CLI.

    Returns the output path on success.
    """
    if output_path.exists() and not force:
        log.debug("Skip render (exists): %s", output_path)
        return output_path

    _check_node_env()

    raw_type = scene.get("template_type") or "flow_steps"
    # Try lowercase first (new style), then UPPER_SNAKE for legacy
    composition_id = _COMPOSITION_ID.get(raw_type) or _COMPOSITION_ID.get(raw_type.upper(), raw_type)
    props = _build_props(scene, fps)
    duration_frames = props.get("durationInFrames", fps * 5)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path = _resolve_existing_audio_path(scene.get("audio_path"))
    render_output_path = (
        output_path.with_name(f"{output_path.stem}_remotion_video.mp4")
        if audio_path
        else output_path
    )

    cmd = [
        "npx",
        "remotion",
        "render",
        "src/Root.tsx",
        composition_id,
        str(render_output_path.resolve()),
        "--props",
        json.dumps(props),
        f"--fps={fps}",
        f"--width={width}",
        f"--height={height}",
        "--codec=h264",
    ]

    log.info("Rendering %s → %s", raw_type, output_path.name)
    log.debug("Remotion cmd: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        cwd=_HYPERFRAME_DIR,
        capture_output=True,
        text=True,
        env={**os.environ},
    )

    if result.returncode != 0:
        log.error("Remotion render failed:\n%s", result.stderr)
        raise RuntimeError(f"Remotion render failed for scene {scene.get('id')}: {result.stderr[-500:]}")

    if audio_path:
        audio_duration_s = _audio_duration_seconds(str(audio_path))
        _mux_audio(render_output_path, audio_path, audio_duration_s, output_path)
        if render_output_path != output_path:
            render_output_path.unlink(missing_ok=True)

    log.info("Rendered: %s", output_path)
    return output_path


def _resolve_existing_audio_path(audio_path: str | None) -> Path | None:
    if not audio_path:
        return None
    p = Path(audio_path)
    if not p.exists():
        log.warning("audio_path not found: %s", audio_path)
        return None
    return p


def _audio_duration_seconds(audio_path: str | None) -> float | None:
    """Return duration in seconds for a recorded audio file via ffprobe."""
    p = _resolve_existing_audio_path(audio_path)
    if not p:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)
        return float(data["streams"][0]["duration"])
    except Exception as exc:
        log.warning("ffprobe failed for %s: %s", audio_path, exc)
        return None


def _audio_duration_frames(audio_path: str | None, fps: int) -> int | None:
    """Return duration in frames for a recorded audio file via ffprobe. None on failure."""
    duration_s = _audio_duration_seconds(audio_path)
    if duration_s is None:
        return None
    return round(duration_s * fps)


def _mux_audio(
    video_path: Path,
    audio_path: Path,
    audio_duration_s: float | None,
    output_path: Path,
) -> None:
    """Replace Remotion's silent/default audio with the scene TTS audio."""
    cmd = [
        _FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
    ]
    if audio_duration_s is not None:
        cmd.extend(["-t", f"{audio_duration_s:.3f}"])
    cmd.append(str(output_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mux failed for {output_path.name}: {result.stderr[-500:]}")


def _extract_bullet_strings(raw: list[Any]) -> list[str]:
    """Extract plain strings from bullet list that may contain dicts."""
    return [b.get("text", str(b)) if isinstance(b, dict) else str(b) for b in raw]


def _fallback_zero_caption_timing(
    caption_segments: Any,
    *,
    duration_frames: int,
    fps: int,
) -> Any:
    """Spread all-zero caption segments across the rendered scene duration."""
    def _ms(value: Any) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    if not isinstance(caption_segments, list) or not caption_segments:
        return caption_segments

    if not all(
        isinstance(seg, dict)
        and _ms(seg.get("start_ms")) == 0
        and _ms(seg.get("end_ms")) == 0
        for seg in caption_segments
    ):
        return caption_segments

    duration_ms = max(1, round(duration_frames * 1000 / fps))
    segment_count = len(caption_segments)
    normalized: list[dict[str, Any]] = []

    for idx, seg in enumerate(caption_segments):
        start_ms = round(duration_ms * idx / segment_count)
        if idx == segment_count - 1:
            end_ms = duration_ms
        else:
            end_ms = round(duration_ms * (idx + 1) / segment_count)
        normalized.append({
            **seg,
            "start_ms": start_ms,
            "end_ms": max(end_ms, start_ms + 1),
        })

    return normalized


def _extract_visual_items(scene: dict[str, Any]) -> list[str]:
    """Extract display items from visual_data (preferred) → bullets → narration fallback."""
    visual_data = scene.get("visual_data") or {}
    narration = scene.get("narration", "")
    raw_bullets = scene.get("bullets") or []
    bullets = _extract_bullet_strings(raw_bullets)

    # visual_data structured extraction
    if visual_data:
        for key in ("steps", "keywords", "nodes", "events", "takeaways"):
            items = visual_data.get(key)
            if items and isinstance(items, list):
                return [str(x) for x in items if x]

    # legacy: bullets → narration snippet
    return bullets or [narration[:120]]


def _build_props(scene: dict[str, Any], fps: int) -> dict[str, Any]:
    """Map scene dict to Remotion component props."""
    template_type = scene.get("template_type") or "flow_steps"
    narration = scene.get("narration", "")
    title = scene.get("title", "")
    visual_data = scene.get("visual_data") or {}
    raw_bullets = scene.get("bullets") or []
    bullets = _extract_bullet_strings(raw_bullets)
    motion_anchors = scene.get("motion_anchors")
    caption_segments = scene.get("caption_segments")

    # Rule 1: audio_path 실제 MP3 길이 기준 — char 추정 금지
    duration_frames = _audio_duration_frames(scene.get("audio_path"), fps)
    if duration_frames is None:
        log.warning("audio_path ffprobe 실패 — 씬 %s에 최소 3초 적용 (char 추정 금지)", scene.get("id"))
        duration_frames = round(3 * fps)

    items = _extract_visual_items(scene)

    # hero_title / TITLE_OPEN
    if template_type in ("hero_title", "TITLE_OPEN"):
        return {
            "title": visual_data.get("title") or title,
            "subtitle": visual_data.get("subtitle") or (narration[:80] if narration else ""),
            "category": visual_data.get("category") or "",
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # summary_card — dedicated SummaryCard composition
    elif template_type == "summary_card":
        takeaways = visual_data.get("takeaways") or bullets or items
        return {
            "takeaways": [str(x) for x in takeaways],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # legacy OUTRO_CTA
    elif template_type == "OUTRO_CTA":
        takeaways = visual_data.get("takeaways") or bullets[:2] or []
        return {
            "nextVideos": [str(x) for x in takeaways[:2]],
            "channelName": os.environ.get("CHANNEL_NAME", ""),
            "durationInFrames": duration_frames,
        }
    # keyword_cards — dedicated KeywordCards composition
    elif template_type == "keyword_cards":
        raw_icons = visual_data.get("icons")
        raw_descs = visual_data.get("descriptions")
        return {
            "title": visual_data.get("title") or title or None,
            "keywords": [str(k) for k in (visual_data.get("keywords") or items)],
            "icons": [str(x) for x in raw_icons] if raw_icons else None,
            "descriptions": [str(x) for x in raw_descs] if raw_descs else None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # legacy LIST_REVEAL
    elif template_type == "LIST_REVEAL":
        return {
            "title": visual_data.get("title") or title,
            "items": visual_data.get("keywords") or items,
            "durationInFrames": duration_frames,
            "motionAnchors": motion_anchors,
            "captionSegments": caption_segments,
        }
    # flow_steps — dedicated FlowSteps composition
    elif template_type in ("flow_steps",):
        raw_steps = visual_data.get("steps") or []
        steps = [str(s) for s in raw_steps if s] or items
        return {
            "title": visual_data.get("title") or title,
            "category": visual_data.get("category") or "",
            "steps": steps,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # architecture_tree — dedicated ArchTree composition
    elif template_type in ("architecture_tree",):
        raw_nodes = visual_data.get("nodes") or []
        # nodes may be list[str] or list[{label, level}]
        nodes: list[Any] = []
        for n in raw_nodes:
            if isinstance(n, dict):
                nodes.append({"label": str(n.get("label", n)), "level": int(n.get("level", 0))})
            else:
                nodes.append({"label": str(n), "level": 0})
        if not nodes:
            nodes = [{"label": s, "level": i} for i, s in enumerate(items[:4])]
        return {
            "title": visual_data.get("title") or visual_data.get("root_label") or title,
            "nodes": nodes,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # timeline — dedicated Timeline composition
    elif template_type == "timeline":
        raw_events = visual_data.get("events") or []
        events = [str(e) for e in raw_events if e] or items
        return {
            "title": visual_data.get("title") or title,
            "category": visual_data.get("category") or "",
            "events": events,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # compare_two — dedicated CompareTwo composition
    elif template_type == "compare_two":
        left = visual_data.get("left_items") or []
        right = visual_data.get("right_items") or []
        return {
            "title": visual_data.get("title") or None,
            "left_title": visual_data.get("left_title") or "A",
            "right_title": visual_data.get("right_title") or "B",
            "left_items": [str(x) for x in left],
            "right_items": [str(x) for x in right],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # table_compare — dedicated TableCompare composition
    elif template_type == "table_compare":
        headers = visual_data.get("headers") or []
        rows = visual_data.get("rows") or []
        return {
            "title": visual_data.get("title") or title or None,
            "headers": [str(h) for h in headers],
            "rows": [[str(c) for c in row] for row in rows],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # quote_highlight — uses existing Quote composition
    elif template_type == "quote_highlight":
        quote_caption_segments = _fallback_zero_caption_timing(
            caption_segments,
            duration_frames=duration_frames,
            fps=fps,
        )
        return {
            "quote": visual_data.get("quote") or narration[:200],
            "source": visual_data.get("source") or "",
            "durationInFrames": duration_frames,
            "captionSegments": quote_caption_segments,
        }
    # before_after — maps before/after to CompareTwo's left/right
    elif template_type == "before_after":
        before_items = visual_data.get("before_items") or []
        after_items = visual_data.get("after_items") or []
        return {
            "title": visual_data.get("title") or None,
            "left_title": visual_data.get("before_title") or "이전",
            "right_title": visual_data.get("after_title") or "이후",
            "left_items": [str(x) for x in before_items],
            "right_items": [str(x) for x in after_items],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # split_title — SplitTitle composition
    elif template_type == "split_title":
        return {
            "title": visual_data.get("title") or title,
            "subtitle": visual_data.get("subtitle") or None,
            "detail": visual_data.get("detail") or None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # underline_title — UnderlineTitle composition
    elif template_type == "underline_title":
        return {
            "title": visual_data.get("title") or title,
            "subtitle": visual_data.get("subtitle") or None,
            "label": visual_data.get("label") or None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # side_accent_title — SideAccentTitle composition
    elif template_type == "side_accent_title":
        return {
            "title": visual_data.get("title") or title,
            "subtitle": visual_data.get("subtitle") or None,
            "tag": visual_data.get("tag") or None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # glass_cards — GlassCards composition
    elif template_type == "glass_cards":
        raw_icons = visual_data.get("icons")
        return {
            "title": visual_data.get("title") or title or None,
            "items": [str(x) for x in (visual_data.get("items") or items)],
            "icons": [str(x) for x in raw_icons] if raw_icons else None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # border_cards — BorderCards composition
    elif template_type == "border_cards":
        raw_labels = visual_data.get("labels")
        return {
            "title": visual_data.get("title") or title or None,
            "items": [str(x) for x in (visual_data.get("items") or items)],
            "labels": [str(x) for x in raw_labels] if raw_labels else None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # number_badge_list — NumberBadgeList composition
    elif template_type == "number_badge_list":
        return {
            "title": visual_data.get("title") or title or None,
            "items": [str(x) for x in (visual_data.get("items") or items)],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # pill_tags — PillTags composition
    elif template_type == "pill_tags":
        raw_tags = visual_data.get("tags") or visual_data.get("keywords") or items
        return {
            "title": visual_data.get("title") or title or None,
            "tags": [str(x) for x in raw_tags],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # fullscreen_text — FullscreenText composition
    elif template_type == "fullscreen_text":
        return {
            "headline": visual_data.get("headline") or visual_data.get("title") or title,
            "subtext": visual_data.get("subtext") or None,
            "label": visual_data.get("label") or None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # two_column_text — TwoColumnText composition
    elif template_type == "two_column_text":
        return {
            "leftTitle": visual_data.get("left_title") or visual_data.get("leftTitle") or None,
            "leftBody": visual_data.get("left_body") or visual_data.get("leftBody") or "",
            "rightTitle": visual_data.get("right_title") or visual_data.get("rightTitle") or None,
            "rightBody": visual_data.get("right_body") or visual_data.get("rightBody") or "",
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # callout_box — CalloutBox composition
    elif template_type == "callout_box":
        return {
            "message": visual_data.get("message") or visual_data.get("quote") or narration[:200],
            "label": visual_data.get("label") or None,
            "note": visual_data.get("note") or None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # bracket_emphasis — BracketEmphasis composition
    elif template_type == "bracket_emphasis":
        return {
            "keyword": visual_data.get("keyword") or visual_data.get("title") or title,
            "context": visual_data.get("context") or None,
            "detail": visual_data.get("detail") or None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # slide_in_list — SlideInList composition
    elif template_type == "slide_in_list":
        return {
            "title": visual_data.get("title") or title or None,
            "items": [str(x) for x in (visual_data.get("items") or items)],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # scale_pop_cards — ScalePopCards composition
    elif template_type == "scale_pop_cards":
        raw_values = visual_data.get("values")
        return {
            "title": visual_data.get("title") or title or None,
            "items": [str(x) for x in (visual_data.get("items") or items)],
            "values": [str(x) for x in raw_values] if raw_values else None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # code_editor — CodeEditorComposition
    elif template_type == "code_editor":
        raw_code = visual_data.get("code") or []
        code_lines = [str(l) for l in raw_code] if raw_code else []
        return {
            "title": visual_data.get("title") or title or None,
            "filename": visual_data.get("filename") or None,
            "language": visual_data.get("language") or "python",
            "code": code_lines,
            "highlight_lines": visual_data.get("highlight_lines") or [],
            "focus_line": visual_data.get("focus_line") or None,
            "typing": bool(visual_data.get("typing", True)),
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # terminal — TerminalComposition
    elif template_type == "terminal":
        raw_lines = visual_data.get("lines") or []
        terminal_lines = [
            {"text": str(ln.get("text", "")), "type": ln.get("type", "output")}
            for ln in raw_lines
            if isinstance(ln, dict)
        ]
        return {
            "title": visual_data.get("title") or title or None,
            "prompt": visual_data.get("prompt") or None,
            "lines": terminal_lines,
            "typing": bool(visual_data.get("typing", True)),
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # chat_conversation — ChatConversationComposition
    elif template_type == "chat_conversation":
        raw_messages = visual_data.get("messages") or []
        messages = [
            {
                "role": msg.get("role", "user"),
                "text": str(msg.get("text", "")),
                **({"name": msg["name"]} if msg.get("name") else {}),
            }
            for msg in raw_messages
            if isinstance(msg, dict)
        ]
        return {
            "title": visual_data.get("title") or title or None,
            "messages": messages,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # architecture_diagram — ArchitectureDiagramComposition
    elif template_type == "architecture_diagram":
        raw_nodes = visual_data.get("nodes") or []
        nodes = [
            {
                "id": str(n.get("id", "")),
                "label": str(n.get("label", "")),
                "type": n.get("type", "secondary"),
                "x": float(n.get("x", 50)),
                "y": float(n.get("y", 50)),
            }
            for n in raw_nodes
            if isinstance(n, dict)
        ]
        raw_edges = visual_data.get("edges") or []
        edges = [
            {
                "from": str(e.get("from", "")),
                "to": str(e.get("to", "")),
                **({"label": e["label"]} if e.get("label") else {}),
                **({"animated": e["animated"]} if e.get("animated") is not None else {}),
            }
            for e in raw_edges
            if isinstance(e, dict)
        ]
        return {
            "title": visual_data.get("title") or title or None,
            "nodes": nodes,
            "edges": edges,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # agent_workflow — AgentWorkflowComposition
    elif template_type == "agent_workflow":
        raw_steps = visual_data.get("steps") or []
        steps = [
            {
                "label": str(s.get("label", "")),
                **({"description": s["description"]} if s.get("description") else {}),
                **({"status": s["status"]} if s.get("status") else {}),
                **({"icon": s["icon"]} if s.get("icon") else {}),
            }
            for s in raw_steps
            if isinstance(s, dict)
        ]
        return {
            "title": visual_data.get("title") or title or None,
            "agent_name": visual_data.get("agent_name") or None,
            "steps": steps,
            "current_step": visual_data.get("current_step") or None,
            "layout": visual_data.get("layout") or "horizontal",
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # keyword_cards_grid — 2×2 grid variant of KeywordCards
    elif template_type == "keyword_cards_grid":
        raw_icons = visual_data.get("icons")
        raw_descs = visual_data.get("descriptions")
        return {
            "title": visual_data.get("title") or title or None,
            "keywords": [str(k) for k in (visual_data.get("keywords") or items)],
            "icons": [str(x) for x in raw_icons] if raw_icons else None,
            "descriptions": [str(x) for x in raw_descs] if raw_descs else None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # keyword_cards_stack — vertical stack variant of KeywordCards
    elif template_type == "keyword_cards_stack":
        raw_descs = visual_data.get("descriptions")
        return {
            "title": visual_data.get("title") or title or None,
            "keywords": [str(k) for k in (visual_data.get("keywords") or items)],
            "descriptions": [str(x) for x in raw_descs] if raw_descs else None,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # timeline_zigzag — zigzag layout variant of Timeline
    elif template_type == "timeline_zigzag":
        raw_events = visual_data.get("events") or []
        events = [str(e) for e in raw_events if e] or items
        return {
            "title": visual_data.get("title") or title,
            "category": visual_data.get("category") or "",
            "events": events,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # timeline_cards — card layout variant of Timeline
    elif template_type == "timeline_cards":
        raw_events = visual_data.get("events") or []
        events = [str(e) for e in raw_events if e] or items
        return {
            "title": visual_data.get("title") or title,
            "category": visual_data.get("category") or "",
            "events": events,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # flow_steps_circle — circular process variant of FlowSteps
    elif template_type == "flow_steps_circle":
        raw_steps = visual_data.get("steps") or []
        steps = [str(s) for s in raw_steps if s] or items
        return {
            "title": visual_data.get("title") or title,
            "category": visual_data.get("category") or "",
            "steps": steps,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # flow_steps_stair — staircase variant of FlowSteps
    elif template_type == "flow_steps_stair":
        raw_steps = visual_data.get("steps") or []
        steps = [str(s) for s in raw_steps if s] or items
        return {
            "title": visual_data.get("title") or title,
            "category": visual_data.get("category") or "",
            "steps": steps,
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # summary_card_split — left/right summary split via CompareTwo
    elif template_type == "summary_card_split":
        left_points = visual_data.get("left_points") or []
        right_points = visual_data.get("right_points") or []
        return {
            "title": visual_data.get("title") or None,
            "left_title": visual_data.get("left_title") or "왼쪽",
            "right_title": visual_data.get("right_title") or "오른쪽",
            "left_items": [str(x) for x in left_points],
            "right_items": [str(x) for x in right_points],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # compare_three — 3-column comparison via TableCompare
    elif template_type == "compare_three":
        col_titles = visual_data.get("col_titles") or []
        rows = visual_data.get("rows") or []
        return {
            "title": visual_data.get("title") or title or None,
            "headers": [str(h) for h in col_titles],
            "rows": [[str(c) for c in row] for row in rows],
            "durationInFrames": duration_frames,
            "captionSegments": caption_segments,
        }
    # EXPLAIN and legacy fallback
    else:
        return {
            "title": visual_data.get("title") or title,
            "bullets": items,
            "durationInFrames": duration_frames,
            "motionAnchors": motion_anchors,
            "captionSegments": caption_segments,
        }
