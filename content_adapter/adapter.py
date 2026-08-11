"""
Content Adapter — top-level entry point.

Runs the 3-layer pipeline and returns an AdapterResult dict.

Output contract:
    {
        "input_type":      "TEXT",
        "content_type":    "LECTURE",
        "scene_strategy":  "lecture_v1",
        "source_text":     "<original text>",
        "adapter_notes": {
            "markdown_detected": bool,
            "title":             str | None,
        }
    }
"""

from __future__ import annotations

from typing import TypedDict

from .content_classifier import classify_content_type
from .input_detector import detect_input_type, is_markdown
from .scene_strategy import select_scene_strategy


class AdapterNotes(TypedDict):
    markdown_detected: bool
    title: str | None


class AdapterResult(TypedDict):
    input_type: str
    content_type: str
    scene_strategy: str
    source_text: str
    adapter_notes: AdapterNotes


def adapt(source_text: str) -> AdapterResult:
    """Run all three adapter layers and return the contract dict."""
    input_type = detect_input_type(source_text)
    content_type = classify_content_type(source_text)
    scene_strategy = select_scene_strategy(content_type)

    markdown_detected = is_markdown(source_text)
    title = _extract_title(source_text) if markdown_detected else None

    return AdapterResult(
        input_type=input_type,
        content_type=content_type,
        scene_strategy=scene_strategy,
        source_text=source_text,
        adapter_notes=AdapterNotes(
            markdown_detected=markdown_detected,
            title=title,
        ),
    )


def _extract_title(text: str) -> str | None:
    """Return the first H1 heading from *text*, or None."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None
