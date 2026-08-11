"""script_summarizer — DEPRECATED visual_summary 생성기.

visual_summary 필드는 template_type + visual_data 체계로 대체됨.
이 모듈은 하위 호환성을 위해 유지하지만 실제 LLM 호출은 수행하지 않는다.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def summarize_narration(narration: str) -> list[str]:  # noqa: ARG001
    """DEPRECATED — visual_summary 생성 중단. 빈 리스트 반환."""
    log.debug("summarize_narration: visual_summary 체계 폐기 — 호출 무시")
    return []


def summarize_scenes(scenes: list[dict]) -> list[dict]:
    """DEPRECATED — visual_summary 필드를 추가하지 않고 scenes를 그대로 반환."""
    log.debug("summarize_scenes: visual_summary 체계 폐기 — scenes 원본 반환")
    return list(scenes)
