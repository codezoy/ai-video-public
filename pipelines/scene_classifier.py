"""Assigns template_type to each scene based on position and content."""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Keyword patterns → template_type (checked in order, first match wins)
_CONTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"비교|vs\.|차이|장단점|vs\s", re.IGNORECASE), "compare_two"),
    (re.compile(r"순서|절차|단계|흐름|flow|process|과정", re.IGNORECASE), "flow_steps"),
    (re.compile(r"계층|트리|구조|hierarchy|tree|레이어|layer", re.IGNORECASE), "architecture_tree"),
    (re.compile(r"버전|역사|history|연도|타임라인|timeline|변화|발전", re.IGNORECASE), "timeline"),
    (re.compile(r"표|테이블|table|비교표|항목", re.IGNORECASE), "table_compare"),
    (re.compile(r"정리|요약|핵심|결론|takeaway|summary", re.IGNORECASE), "summary_card"),
    (re.compile(r"개념|용어|키워드|정의|란\?|이란|란\s", re.IGNORECASE), "keyword_cards"),
]

_VISUAL_TYPE_MAP: dict[str, str] = {
    "mermaid":  "architecture_tree",
    "code":     "flow_steps",
    "card":     "keyword_cards",
    "bullets":  "flow_steps",
    "list":     "keyword_cards",
    "diagram":  "architecture_tree",
    "quote":    "summary_card",
    # "text" intentionally excluded — falls through to keyword-based classification
}


def _classify_by_content(scene: dict[str, Any]) -> str:
    """Classify a middle scene by narration keywords first, then visual_type hints."""
    narration = scene.get("narration", "") + " " + scene.get("title", "")
    for pattern, template_type in _CONTENT_RULES:
        if pattern.search(narration):
            return template_type

    visual_type = (scene.get("visual_type") or "").lower()
    if visual_type in _VISUAL_TYPE_MAP:
        return _VISUAL_TYPE_MAP[visual_type]

    bullets = scene.get("bullets") or []
    if len(bullets) >= 3:
        return "keyword_cards"

    return "flow_steps"


def classify(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return new scene list with template_type assigned.

    Rules:
    - First scene → hero_title
    - Last scene  → summary_card
    - Middle scenes → derived from visual_type / narration keywords
    """
    if not scenes:
        return scenes

    result: list[dict[str, Any]] = []
    last_idx = len(scenes) - 1

    for i, scene in enumerate(scenes):
        scene_copy = dict(scene)

        if i == 0:
            scene_copy["template_type"] = "hero_title"
        elif i == last_idx:
            scene_copy["template_type"] = "summary_card"
        else:
            scene_copy["template_type"] = _classify_by_content(scene)

        logger.debug(
            "Scene %d (%s) → %s",
            scene.get("id", i),
            scene.get("title", "")[:30],
            scene_copy["template_type"],
        )
        result.append(scene_copy)

    logger.info(
        "Classified %d scenes: first=%s last=%s",
        len(result),
        result[0]["template_type"] if result else "-",
        result[-1]["template_type"] if result else "-",
    )
    return result
