"""Scene Budget — target_duration_sec → max_scene_count 제한 시스템.

ISSUE-005-01 fix: 영상 길이에 비례한 씬 수 상한을 두고 초과 시
scene merge / prune / summary compression 을 자동 수행.

Generation Profile 기반으로 동작하며, get_profile_budget()으로 통합 접근한다.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

_DEFAULT_NARRATION_KEY = "narration"
_DEFAULT_TITLE_KEY = "title"


_DEFAULT_SCENE_DURATION_SEC = 15
_SCENE_COUNT_MAX = 150  # raised from 60 to support long-form videos (30min = 120 scenes)


def get_max_scenes(target_duration_sec: int) -> int:
    """target_duration_sec → Scene-first Duration Contract 기반 씬 수.

    direct_scene_gen.py 와 동일한 공식: round(target / 15), clamp [1, 60].
    generation_profiles 의 legacy max_scenes 는 사용하지 않는다.
    """
    scene_count_raw = round(target_duration_sec / _DEFAULT_SCENE_DURATION_SEC)
    return max(1, min(scene_count_raw, _SCENE_COUNT_MAX))


def get_min_scenes(target_duration_sec: int) -> int:
    """target_duration_sec 에 대한 최소 씬 수."""
    try:
        from generation_profiles import select_profile
        _, cfg = select_profile(target_duration_sec)
        return cfg["min_scenes"]
    except ImportError:
        return 3


def get_max_scene_narration_chars(target_duration_sec: int) -> int:
    """씬당 최대 나레이션 글자 수."""
    try:
        from generation_profiles import select_profile
        _, cfg = select_profile(target_duration_sec)
        return cfg["max_scene_narration_chars"]
    except ImportError:
        return 180


def get_max_scene_duration_sec(target_duration_sec: int) -> int:
    """씬당 최대 길이(초). 평균 + 여유치."""
    max_scenes = get_max_scenes(target_duration_sec)
    return max(15, (target_duration_sec // max_scenes) + 5)


def apply_budget(
    scenes: list[dict[str, Any]],
    target_duration_sec: int,
    *,
    narration_key: str = _DEFAULT_NARRATION_KEY,
    keyword_hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    """씬 리스트에 budget 제한 적용. 초과 시 prune → merge 순서로 축소.

    keyword_hints: 해당 키워드를 포함한 씬은 prune 대상에서 제외 (정보 보존).
    """
    max_count = get_max_scenes(target_duration_sec)
    original_count = len(scenes)

    if original_count <= max_count:
        log.info(
            "[SceneBudget] skip=true reason=scene_count_within_limit count=%d max=%d",
            original_count,
            max_count,
        )
        return scenes

    log.info(
        "scene_budget: %d scenes exceeds max %d for %ds target — pruning",
        original_count,
        max_count,
        target_duration_sec,
    )

    # 짧은 영상(≤60s): 긴 씬 우선 제거 → 총 재생시간 단축
    if target_duration_sec <= 60:
        result = _prune_long(scenes, max_count, narration_key=narration_key, keyword_hints=keyword_hints)
    else:
        result = _prune_short(scenes, max_count, narration_key=narration_key, keyword_hints=keyword_hints)

    if len(result) > max_count:
        result = _merge_adjacent(result, max_count, narration_key=narration_key)

    log.info(
        "scene_budget: reduced %d → %d scenes",
        original_count,
        len(result),
    )
    return result


def _contains_keywords(scene: dict[str, Any], narration_key: str, keywords: list[str]) -> bool:
    """씬의 title 또는 narration에 키워드가 포함되어 있으면 True."""
    text = (scene.get(_DEFAULT_TITLE_KEY, "") + " " + scene.get(narration_key, "")).lower()
    return any(kw.lower() in text for kw in keywords)


def _prune_short(
    scenes: list[dict[str, Any]],
    max_count: int,
    *,
    narration_key: str,
    keyword_hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    """나레이션이 짧은 씬을 우선 제거. 첫/마지막 씬은 보존.
    keyword_hints 포함 씬은 prune 대상에서 제외.
    """
    if len(scenes) <= max_count:
        return scenes

    remove_count = len(scenes) - max_count
    kw = keyword_hints or []

    # Middle scenes only; skip keyword-protected scenes
    candidates = [
        (i, len(s.get(narration_key, "")))
        for i, s in enumerate(scenes)
        if 0 < i < len(scenes) - 1 and not _contains_keywords(s, narration_key, kw)
    ]
    candidates.sort(key=lambda x: x[1])

    to_remove = {idx for idx, _ in candidates[:remove_count]}
    for idx in sorted(to_remove):
        s = scenes[idx]
        narr_preview = s.get(narration_key, "")[:40].replace("\n", " ")
        log.warning(
            "[SceneBudget][PRUNE-SHORT] 씬 제거: idx=%d title=%r narration_preview=%r",
            idx, s.get(_DEFAULT_TITLE_KEY, ""), narr_preview,
        )

    result = [s for i, s in enumerate(scenes) if i not in to_remove]

    # Tail fallback: keyword-protected 씬 우선 건너뜀; 모두 보호된 경우 마지막 수단으로 제거
    while len(result) > max_count and len(result) > 2:
        fallback_idx = next(
            (i for i in range(1, len(result) - 1)
             if not _contains_keywords(result[i], narration_key, kw)),
            None,
        )
        if fallback_idx is None:
            fallback_idx = len(result) - 2
            log.warning(
                "[SceneBudget][PRUNE-SHORT] 키워드 보호 씬 강제 제거(예산 초과 — 비보호 후보 없음): title=%r",
                result[fallback_idx].get(_DEFAULT_TITLE_KEY, ""),
            )
        s = result[fallback_idx]
        narr_preview = s.get(narration_key, "")[:40].replace("\n", " ")
        log.warning(
            "[SceneBudget][PRUNE-SHORT] 씬 제거(tail fallback): title=%r narration_preview=%r",
            s.get(_DEFAULT_TITLE_KEY, ""), narr_preview,
        )
        result.pop(fallback_idx)

    return result


def _prune_long(
    scenes: list[dict[str, Any]],
    max_count: int,
    *,
    narration_key: str,
    keyword_hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    """나레이션이 긴 씬을 우선 제거. 첫/마지막 씬은 보존. 짧은 영상 모드용.
    keyword_hints 포함 씬은 prune 대상에서 제외.
    """
    if len(scenes) <= max_count:
        return scenes

    remove_count = len(scenes) - max_count
    kw = keyword_hints or []

    candidates = [
        (i, len(s.get(narration_key, "")))
        for i, s in enumerate(scenes)
        if 0 < i < len(scenes) - 1 and not _contains_keywords(s, narration_key, kw)
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)

    to_remove = {idx for idx, _ in candidates[:remove_count]}
    for idx in sorted(to_remove):
        s = scenes[idx]
        narr_preview = s.get(narration_key, "")[:40].replace("\n", " ")
        log.warning(
            "[SceneBudget][PRUNE-LONG] 씬 제거: idx=%d title=%r narration_preview=%r",
            idx, s.get(_DEFAULT_TITLE_KEY, ""), narr_preview,
        )

    result = [s for i, s in enumerate(scenes) if i not in to_remove]

    # Tail fallback: keyword-protected 씬 우선 건너뜀; 모두 보호된 경우 마지막 수단으로 제거
    while len(result) > max_count and len(result) > 2:
        fallback_idx = next(
            (i for i in range(1, len(result) - 1)
             if not _contains_keywords(result[i], narration_key, kw)),
            None,
        )
        if fallback_idx is None:
            fallback_idx = len(result) - 2
            log.warning(
                "[SceneBudget][PRUNE-LONG] 키워드 보호 씬 강제 제거(예산 초과 — 비보호 후보 없음): title=%r",
                result[fallback_idx].get(_DEFAULT_TITLE_KEY, ""),
            )
        s = result[fallback_idx]
        narr_preview = s.get(narration_key, "")[:40].replace("\n", " ")
        log.warning(
            "[SceneBudget][PRUNE-LONG] 씬 제거(tail fallback): title=%r narration_preview=%r",
            s.get(_DEFAULT_TITLE_KEY, ""), narr_preview,
        )
        result.pop(fallback_idx)

    return result


def _merge_adjacent(
    scenes: list[dict[str, Any]],
    max_count: int,
    *,
    narration_key: str,
) -> list[dict[str, Any]]:
    """인접 씬 쌍의 나레이션을 합산하여 씬 수 축소."""
    result = list(scenes)

    while len(result) > max_count and len(result) >= 2:
        # Find adjacent pair with shortest combined narration
        best_i = 0
        best_len = float("inf")
        for i in range(len(result) - 1):
            combined = len(result[i].get(narration_key, "")) + len(
                result[i + 1].get(narration_key, "")
            )
            if combined < best_len:
                best_len = combined
                best_i = i

        a = result[best_i]
        b = result[best_i + 1]
        title_a = a.get(_DEFAULT_TITLE_KEY, "")
        title_b = b.get(_DEFAULT_TITLE_KEY, "")
        log.warning(
            "[SceneBudget][MERGE] 씬 병합: idx=%d+%d title=%r + %r",
            best_i, best_i + 1, title_a, title_b,
        )

        merged = dict(a)
        merged[narration_key] = (
            a.get(narration_key, "").rstrip()
            + " "
            + b.get(narration_key, "").lstrip()
        ).strip()
        if title_b and title_b != title_a:
            merged[_DEFAULT_TITLE_KEY] = f"{title_a} / {title_b}"

        result = result[:best_i] + [merged] + result[best_i + 2:]

    return result
