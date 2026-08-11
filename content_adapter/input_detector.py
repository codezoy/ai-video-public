"""
Input Type Layer — detects the type of raw input source.

MVP: TEXT only (.txt / .md / .markdown / plain string).
Markdown is treated as TEXT with markdown_detected=True in adapter_notes.
"""

from __future__ import annotations

import pathlib


# Markdown extensions recognised within the TEXT type
_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
_TEXT_EXTENSIONS = {".txt"} | _MARKDOWN_EXTENSIONS


def detect_input_type(source: str) -> str:
    """Return the input type for *source*.

    Always returns ``"TEXT"`` in the current MVP.
    Raises ``ValueError`` if the source is empty.
    """
    if not source or not source.strip():
        raise ValueError("source must be a non-empty string")
    return "TEXT"


def is_markdown(source: str) -> bool:
    """Return True if *source* looks like a file path with a markdown extension,
    or if the raw text contains typical Markdown indicators (``#``, ``---``, ``**``).
    """
    path = pathlib.Path(source)
    if path.suffix.lower() in _MARKDOWN_EXTENSIONS:
        return True
    # Heuristic: check for common Markdown patterns in the raw text
    indicators = ("#", "---", "**", "```", "- ", "* ")
    return any(line.startswith(ind) for line in source.splitlines()[:20] for ind in indicators)
