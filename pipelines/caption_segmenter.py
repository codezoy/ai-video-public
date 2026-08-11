# DEPRECATED: 2026-05-30 — 표준 경로에서 미호출. REMOVAL_CANDIDATE: 2026-06-30
"""caption_segmenter.py — word_timestamps → phrase-level caption segments.

word-level timestamps 를 문장/어구 단위 캡션으로 묶어 반환한다.
어절 개수 기반 분리 대신 한국어 문장 경계(sentence-end / phrase-boundary)를 기준으로 분리.
출력: List[CaptionSegment] (text, start_ms, end_ms, word_timestamps)
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict

log = logging.getLogger(__name__)

# 캡션 그룹핑 파라미터 (Korean sentence/phrase rhythm — 15~35자 목표)
MAX_SEGMENT_MS = 3500    # 한 캡션 최대 지속 시간 (ms)
GAP_SPLIT_MS = 400       # 단어 간 gap 이 이 이상이면 새 캡션으로 분리 (발화 휴지)
TARGET_MAX_CHARS = 35    # 이 글자 수 초과 + 경계어면 분리
HARD_MAX_CHARS = 50      # 경계어 무관하게 강제 분리 (최대 허용)

# 한국어 문장 종결 패턴 (습니다/어요/해요 류 종결어미, 문장부호)
_SENTENCE_END = re.compile(
    r"""(?x)
    (?:습니다|니다|해요|어요|아요|세요|셔요|예요|이에요|죠|나요|군요|네요|
       는걸요|는군요|랍니다|답니다|겠습니다|겠어요)
    \s*[.!?！？。]?\s*$
    |
    [.!?！？。]\s*$
    """
)

# 한국어 구/절 경계 패턴 (연결어미 — 종결은 아니지만 자연스러운 분리점)
_PHRASE_BOUNDARY = re.compile(
    r"""(?x)
    (?:하고|이고|하며|이며|하면서|이면서|하여|이어|
       하면|이면|하지만|이지만|지만|어서|아서|여서|
       거나|든지|지만|더라도|할수록|할때|때문에|위해서?|
       통해서?|으로서?|로서?)\s*$
    """
)


class WordTimestamp(TypedDict):
    word: str
    start_ms: int
    end_ms: int


class CaptionSegment(TypedDict):
    text: str
    start_ms: int
    end_ms: int
    word_timestamps: list[WordTimestamp]


def _is_sentence_end(word: str) -> bool:
    return bool(_SENTENCE_END.search(word.strip()))


def _is_phrase_boundary(word: str) -> bool:
    return bool(_PHRASE_BOUNDARY.search(word.strip()))


def segment(word_timestamps: list[WordTimestamp]) -> list[CaptionSegment]:
    """word_timestamps 목록을 phrase-level caption segments 로 그룹핑.

    그룹핑 규칙 (우선순위 순):
    1. [강제] 단어 간 gap >= GAP_SPLIT_MS → 새 세그먼트 시작 (발화 휴지)
    2. [강제] 현재 세그먼트 지속 시간 >= MAX_SEGMENT_MS → 분리
    3. [의미] 누적 글자 수 >= TARGET_MAX_CHARS + 문장종결/구경계어 → 분리
    4. [강제] 누적 글자 수 >= HARD_MAX_CHARS → 분리 (경계 무관)

    규칙 3·4는 단어 추가 후 평가 (post-word) → 문장 중간 분리 방지

    Args:
        word_timestamps: whisper_align.align() 반환값

    Returns:
        [{"text": str, "start_ms": int, "end_ms": int, "word_timestamps": [...]}, ...]
    """
    if not word_timestamps:
        return []

    segments: list[CaptionSegment] = []
    current_words: list[str] = []
    current_wts: list[WordTimestamp] = []
    seg_start_ms = word_timestamps[0]["start_ms"]
    prev_end_ms = word_timestamps[0]["start_ms"]

    def flush(end_ms: int) -> None:
        if not current_words:
            return
        segments.append(
            CaptionSegment(
                text=" ".join(current_words),
                start_ms=seg_start_ms,
                end_ms=end_ms,
                word_timestamps=list(current_wts),
            )
        )

    for wt in word_timestamps:
        word = wt["word"].strip()
        if not word:
            continue

        gap = wt["start_ms"] - prev_end_ms
        duration = prev_end_ms - seg_start_ms  # 현재까지 누적 시간 (incoming word 제외)

        # pre-word 강제 분리: 발화 휴지 또는 시간 초과
        hard_pre = (gap >= GAP_SPLIT_MS and current_words) or (duration >= MAX_SEGMENT_MS and current_words)
        if hard_pre and current_words:
            flush(prev_end_ms)
            current_words = []
            current_wts = []
            seg_start_ms = wt["start_ms"]

        # 현재 단어 추가
        current_words.append(word)
        current_wts.append(wt)
        prev_end_ms = wt["end_ms"]

        # post-word 의미/강제 분리
        char_count = sum(len(w) for w in current_words)

        if char_count >= HARD_MAX_CHARS:
            # 강제 분리 — 경계 무관
            flush(wt["end_ms"])
            current_words = []
            current_wts = []
            seg_start_ms = wt["end_ms"]
        elif char_count >= TARGET_MAX_CHARS and (_is_sentence_end(word) or _is_phrase_boundary(word)):
            # 의미 경계 분리
            flush(wt["end_ms"])
            current_words = []
            current_wts = []
            seg_start_ms = wt["end_ms"]

    flush(prev_end_ms)

    log.info("caption_segmenter: %d words → %d segments", len(word_timestamps), len(segments))
    return segments


def main() -> None:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Generate caption segments from word timestamps.")
    parser.add_argument("word_timestamps_json", type=Path)
    parser.add_argument("--output", type=Path, help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    wts: list[WordTimestamp] = json.loads(args.word_timestamps_json.read_text())
    result = segment(wts)

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output)
        print(f"Saved {len(result)} caption segments → {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
