"""
Scene Strategy Layer — selects the scene generation strategy for a given content type.

MVP: ``"LECTURE"`` → ``"lecture_v1"``

lecture_v1 scene flow:
    1. Hook / 도입
    2. 핵심 개념 1
    3. 핵심 개념 2
    4. 구조 설명
    5. 예시
    6. 요약 / 마무리
"""

from __future__ import annotations

_STRATEGY_MAP: dict[str, str] = {
    "LECTURE": "lecture_v1",
}

# lecture_v1: 6-scene plan consumed by direct_scene_gen._build_scene_plan_context()
_LECTURE_V1_PLAN: dict = {
    "strategy": "lecture_v1",
    "scene_count": 6,
    "scenes": [
        {
            "scene_id": 1,
            "purpose": "hook",
            "title": "도입 — 왜 중요한가?",
            "message": "핵심 질문으로 시작해 호기심을 유발한다",
            "visual_type": "single_text",
            "narration_hint": "반드시 '왜 ~?' 형태의 질문으로 시작하라",
        },
        {
            "scene_id": 2,
            "purpose": "core_concept_1",
            "title": "핵심 개념 1",
            "message": "첫 번째 핵심 개념을 구체적으로 설명한다",
            "visual_type": "bullet_list",
            "narration_hint": "개념의 본질과 왜 중요한지를 설명하라",
        },
        {
            "scene_id": 3,
            "purpose": "core_concept_2",
            "title": "핵심 개념 2",
            "message": "두 번째 핵심 개념 또는 첫 번째 개념과의 비교",
            "visual_type": "compare_two",
            "narration_hint": "두 관점을 비교하거나 심화 개념을 전개하라",
        },
        {
            "scene_id": 4,
            "purpose": "structure",
            "title": "구조 설명",
            "message": "전체 구조나 원리를 체계적으로 제시한다",
            "visual_type": "single_text",
            "narration_hint": "계층 구조, 흐름, 원칙 중 하나를 명확히 정리하라",
        },
        {
            "scene_id": 5,
            "purpose": "example",
            "title": "실제 사례",
            "message": "실제 서비스·기업·사건 사례로 개념을 구체화한다",
            "visual_type": "single_text",
            "narration_hint": "실제 이름(기업, 서비스, 사건)을 반드시 언급하라",
        },
        {
            "scene_id": 6,
            "purpose": "summary",
            "title": "요약 — 오늘 기억할 것",
            "message": "핵심 인사이트 3가지로 마무리한다",
            "visual_type": "single_text",
            "narration_hint": "summary_card 템플릿, takeaways 3개 이상, 구체적 인사이트",
        },
    ],
}

_PLAN_MAP: dict[str, dict] = {
    "lecture_v1": _LECTURE_V1_PLAN,
}


def select_scene_strategy(content_type: str) -> str:
    """Return the scene strategy name for *content_type*.

    Raises ``ValueError`` for unknown content types.
    """
    strategy = _STRATEGY_MAP.get(content_type)
    if strategy is None:
        raise ValueError(f"No scene strategy registered for content_type={content_type!r}")
    return strategy


def build_scene_plan(scene_strategy: str) -> dict:
    """Return the scene plan dict for *scene_strategy*.

    Raises ``ValueError`` for unknown strategies.
    """
    plan = _PLAN_MAP.get(scene_strategy)
    if plan is None:
        raise ValueError(f"No scene plan registered for scene_strategy={scene_strategy!r}")
    return plan
