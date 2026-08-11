"""motion_anchor_gen.py — word_timestamps → motion_anchor 자동 생성.

각 scene 의 bullets 와 word_timestamps 를 매칭해 bullet 등장 트리거 anchor 생성.
출력: List[MotionAnchor] (trigger_word, appear_at_ms, bullet_idx)
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TypedDict

from whisper_align import WordTimestamp  # type: ignore[import]

log = logging.getLogger(__name__)

MIN_ANCHORS_PER_SCENE = 1
MAX_ANCHORS_PER_SCENE = 5
LOOK_AHEAD_MS = 200  # 단어 검출 후 bullet 등장까지 딜레이 (ms)


class MotionAnchor(TypedDict):
    trigger_word: str
    appear_at_ms: int
    bullet_idx: int


def generate_anchors(
    scene: dict,
    word_timestamps: list[WordTimestamp],
) -> list[MotionAnchor]:
    """scene 의 bullets 와 word_timestamps 를 매칭해 motion_anchors 생성.

    매칭 전략:
    1. 각 bullet 첫 번째 의미 단어를 word_timestamps 에서 탐색
    2. 매칭 실패 시 균등 분배 fallback
    3. 결과는 3~5개 범위로 클리핑

    Args:
        scene: scenes.json 의 단일 scene dict (bullets, narration 포함)
        word_timestamps: whisper_align.align() 반환값

    Returns:
        [{"trigger_word": str, "appear_at_ms": int, "bullet_idx": int}, ...]
    """
    raw_bullets: list = scene.get("bullets") or []
    # bullets 가 객체 배열이면 text 필드 추출, 문자열 배열이면 그대로 사용
    bullets: list[str] = [
        b["text"] if isinstance(b, dict) else b for b in raw_bullets
    ]
    narration: str = scene.get("narration", "")

    if not bullets:
        log.debug("Scene %s has no bullets, skipping anchor gen", scene.get("id"))
        return []

    audio_duration_sec: float | None = scene.get("audio_duration_sec")

    if not word_timestamps:
        log.warning("No word_timestamps for scene %s, using uniform fallback", scene.get("id"))
        return _uniform_fallback(bullets, narration, audio_duration_sec)

    anchors: list[MotionAnchor] = []
    used_indices: set[int] = set()

    for bullet_idx, bullet in enumerate(bullets):
        anchor = _match_bullet(bullet, bullet_idx, word_timestamps, used_indices)
        if anchor:
            anchors.append(anchor)
        else:
            # Fallback: uniform spacing
            total_ms = word_timestamps[-1]["end_ms"] if word_timestamps else 5000
            appear_at = round(total_ms * (bullet_idx + 1) / (len(bullets) + 1))
            anchors.append(
                MotionAnchor(
                    trigger_word=_first_word(bullet),
                    appear_at_ms=appear_at,
                    bullet_idx=bullet_idx,
                )
            )

    # 3~5개 범위 클리핑
    anchors = anchors[:MAX_ANCHORS_PER_SCENE]
    if len(anchors) < MIN_ANCHORS_PER_SCENE and word_timestamps:
        # 최소 1개 보장
        anchors = [
            MotionAnchor(
                trigger_word=word_timestamps[0]["word"],
                appear_at_ms=word_timestamps[0]["start_ms"],
                bullet_idx=0,
            )
        ]

    log.info("Scene %s: %d motion_anchors generated", scene.get("id"), len(anchors))
    return anchors


def _match_bullet(
    bullet: str,
    bullet_idx: int,
    words: list[WordTimestamp],
    used_indices: set[int],
) -> MotionAnchor | None:
    """bullet 첫 번째 의미 단어를 word_timestamps 에서 탐색."""
    keywords = _extract_keywords(bullet)
    if not keywords:
        return None

    for keyword in keywords:
        kw_lower = keyword.lower()
        for i, wt in enumerate(words):
            if i in used_indices:
                continue
            word_lower = re.sub(r"[^\w]", "", wt["word"].lower())
            if kw_lower in word_lower or word_lower in kw_lower:
                used_indices.add(i)
                return MotionAnchor(
                    trigger_word=wt["word"],
                    appear_at_ms=max(0, wt["start_ms"] - LOOK_AHEAD_MS),
                    bullet_idx=bullet_idx,
                )
    return None


def _extract_keywords(text: str) -> list[str]:
    """불용어 제거 후 의미 키워드 추출."""
    STOP_WORDS = {
        "은", "는", "이", "가", "을", "를", "의", "에", "에서", "로", "으로",
        "와", "과", "도", "만", "부터", "까지", "하고", "이고", "이며", "및",
        "그", "이", "저", "것", "수", "등", "들", "때", "후", "전", "내",
        "the", "a", "an", "and", "or", "is", "are", "was", "were", "to", "of",
        "in", "on", "at", "for", "with", "by",
    }
    tokens = re.findall(r"[\w가-힣]+", text)
    keywords = [t for t in tokens if t.lower() not in STOP_WORDS and len(t) >= 2]
    return keywords[:3]  # 상위 3개만 시도


def _first_word(text: str) -> str:
    """텍스트에서 첫 번째 단어 추출."""
    words = text.strip().split()
    return words[0] if words else text[:10]


def _uniform_fallback(
    bullets: list[str],
    narration: str,
    audio_duration_sec: float | None = None,
) -> list[MotionAnchor]:
    """word_timestamps 없을 때 균등 배치.

    audio_duration_sec 가 있으면 실제 오디오 길이를 사용한다.
    없으면 narration 글자 수 기반 추정(5 chars/sec)으로 fallback.
    """
    if audio_duration_sec and audio_duration_sec > 0:
        total_ms = max(3000, round(audio_duration_sec * 1000))
    else:
        CHARS_PER_SECOND = 5.0  # 한국어 평균 발화 속도 근사 (fallback only)
        total_ms = max(3000, round(len(narration) / CHARS_PER_SECOND * 1000))
    n = min(len(bullets), MAX_ANCHORS_PER_SCENE)
    anchors: list[MotionAnchor] = []
    for i in range(n):
        appear_at = round(total_ms * (i + 1) / (n + 1))
        anchors.append(
            MotionAnchor(
                trigger_word=_first_word(bullets[i]),
                appear_at_ms=appear_at,
                bullet_idx=i,
            )
        )
    return anchors


def main() -> None:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Generate motion anchors from word timestamps.")
    parser.add_argument("scene_json", type=Path, help="scenes.json file")
    parser.add_argument("word_timestamps_json", type=Path, help="word_timestamps JSON (per-scene or flat list)")
    parser.add_argument("--scene-id", help="Process only this scene id")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    scenes: list[dict] = json.loads(args.scene_json.read_text())
    all_wts: dict | list = json.loads(args.word_timestamps_json.read_text())

    for scene in scenes:
        sid = scene.get("id", "")
        if args.scene_id and sid != args.scene_id:
            continue
        wts = all_wts.get(sid, []) if isinstance(all_wts, dict) else all_wts
        anchors = generate_anchors(scene, wts)
        print(f"Scene {sid}: {json.dumps(anchors, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
