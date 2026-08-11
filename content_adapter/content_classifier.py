"""
Content Type Layer — classifies TEXT input into a content type.

MVP: always returns ``"LECTURE"``.

Future candidates (not implemented):
    NEWS          — breaking news / event-driven articles
    SUMMARY       — condensed recap / bullet-point content
    TECH_EXPLAIN  — technical deep-dive / architecture walkthrough
    GENERAL       — catch-all for unclassified content
"""

from __future__ import annotations


def classify_content_type(text: str) -> str:
    """Return the content type for *text*.

    Always returns ``"LECTURE"`` in the current MVP.
    """
    return "LECTURE"
